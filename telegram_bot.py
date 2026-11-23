"""Bot do Telegram: envia cada vídeo pronto com os botões Aprovar / Reprovar / Editar legenda.

Comandos no chat:
  /start            mostra o ID deste chat (para colocar no .env)
  /gerar [streamer] busca clipes, monta um vídeo e envia para aprovação
  /pendentes        reenvia os vídeos que ainda não foram decididos
  /status           resumo de aprovados, reprovados e pendentes
  /pausar /retomar  liga e desliga a geração automática nos horários do .env
"""
import json
import os
import shutil
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

import requests
from requests_toolbelt import MultipartEncoder, MultipartEncoderMonitor

import banco
import coletar
import montar
import nuvem
import metricool
import youtube
from progresso import Progresso
from config import (APROVADOS, HORARIOS, MAX_MINUTOS, NA_NUVEM, POR_HORARIO, PRONTOS, STREAMERS,
                    TELEGRAM_CHAT_ID, TELEGRAM_TOKEN)

API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
MOTIVOS = {
    "corte": "Corte ruim",
    "fraco": "Clipe fraco",
    "direitos": "Problema de direitos",
    "outro": "Outro",
}
_ocupado = threading.Lock()
_fim_do_turno = None  # hora (time.time) em que o turno na nuvem acaba


def _auto_ligado():
    return banco.meta("auto_pausado", "0") != "1"


def chamar(metodo, **dados):
    arquivos = dados.pop("_arquivos", None)
    for k, v in list(dados.items()):
        if isinstance(v, (dict, list)):
            dados[k] = json.dumps(v)
    r = requests.post(f"{API}/{metodo}", data=dados, files=arquivos, timeout=300)
    resp = r.json()
    if not resp.get("ok"):
        raise RuntimeError(f"Telegram {metodo}: {resp.get('description')}")
    return resp["result"]


def avisar(texto, chat=None):
    chamar("sendMessage", chat_id=chat or TELEGRAM_CHAT_ID, text=texto)


def botoes_decisao(vid):
    return {"inline_keyboard": [
        [{"text": "✅ Aprovar", "callback_data": f"ap:{vid}"},
         {"text": "❌ Reprovar", "callback_data": f"rp:{vid}"}],
        [{"text": "✏️ Editar legenda", "callback_data": f"ed:{vid}"}],
    ]}


def texto_video(v):
    clipes = json.loads(v["clipes"])
    return (f"🎬 Vídeo #{v['id']} · {v['streamer']} · {v['duracao']:.0f}s · {len(clipes)} clipes\n\n"
            f"Legenda sugerida:\n{v['legenda']}")[:1024]


def nova_barra(titulo, chat=None):
    chat = chat or TELEGRAM_CHAT_ID
    return Progresso(
        titulo,
        enviar=lambda t: chamar("sendMessage", chat_id=chat, text=t)["message_id"],
        editar=lambda mid, t: chamar("editMessageText", chat_id=chat, message_id=mid, text=t),
    )


def _ocultar(texto):
    """Nunca mostra o token em mensagens de erro."""
    return str(texto).replace(TELEGRAM_TOKEN, "***") if TELEGRAM_TOKEN else str(texto)


def criar_previa(arquivo):
    """Versão leve (720p, ~10 MB) só para assistir no Telegram; o arquivo em 1080p fica para publicar."""
    previa = Path(arquivo).with_name(Path(arquivo).stem + "_previa.mp4")
    if not previa.exists():
        montar.rodar(["ffmpeg", "-y", "-loglevel", "error", "-i", str(arquivo),
                      "-vf", "scale=720:1280", "-c:v", "libx264", "-preset", "veryfast",
                      "-b:v", "850k", "-maxrate", "1000k", "-bufsize", "2000k",
                      "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(previa)])
    return previa


def garantir_arquivo(vid):
    """Na nuvem o computador muda a cada turno: baixa o vídeo da Release se ele não estiver aqui."""
    v = banco.video(vid)
    if not Path(v["arquivo"]).exists() and v.get("url"):
        destino = PRONTOS / Path(v["url"]).name
        with requests.get(v["url"], stream=True, timeout=120) as resp:
            resp.raise_for_status()
            with open(destino, "wb") as f:
                for parte in resp.iter_content(1 << 20):
                    f.write(parte)
        banco.atualizar_video(vid, arquivo=str(destino))
        v = banco.video(vid)
    return v


def publicar_youtube(vid, chat=None):
    """Publica o vídeo aprovado no YouTube Shorts e avisa no Telegram."""
    if not youtube.configurado():
        return
    v = banco.video(vid)
    if v.get("youtube"):
        avisar(f"O vídeo #{vid} já está no YouTube: {v['youtube']}", chat)
        return
    barra = nova_barra(f"▶️ YouTube · vídeo #{vid}", chat)
    try:
        barra.atualizar(0, "Preparando o vídeo", True)
        v = garantir_arquivo(vid)
        clipes = [c for c in banco.clipes_do_video(vid)]
        titulo, descricao = youtube.titulo_e_descricao(v, clipes)
        link, privacidade = youtube.publicar(v["arquivo"], titulo, descricao,
                                             tags=[v["streamer"], "twitch", "clipes", "shorts"],
                                             prog=barra.atualizar)
        banco.atualizar_video(vid, youtube=link)
        nuvem.salvar_estado(f"vídeo {vid} no YouTube")
        extra = ("\n\nO YouTube deixou como PRIVADO (o projeto do Google ainda não passou pela análise). "
                 "Abra o link e mude para Público.") if privacidade == "private" and youtube.PRIVACIDADE != "private" else ""
        avisar(f"✅ Vídeo #{vid} publicado no YouTube: {link}{extra}", chat)
    except Exception as e:
        print(_ocultar(traceback.format_exc()))
        avisar(f"Não consegui publicar o vídeo #{vid} no YouTube: {_ocultar(e)[:300]}\n"
               f"Para tentar de novo: /publicar {vid}", chat)


def publicar_metricool(vid, chat=None):
    """Agenda o vídeo aprovado no Metricool para as redes configuradas."""
    v = banco.video(vid)
    if v.get("youtube"):
        avisar(f"O vídeo #{vid} já foi enviado para publicação.", chat)
        return
    try:
        titulo, descricao = youtube.titulo_e_descricao(v, banco.clipes_do_video(vid))
        post_id, hora = metricool.agendar(v.get("url"), titulo, descricao)
        banco.atualizar_video(vid, youtube=f"metricool:{post_id or 'agendado'}")
        nuvem.salvar_estado(f"vídeo {vid} agendado no Metricool")
        avisar(f"📅 Vídeo #{vid} agendado no Metricool para as {hora} em: {', '.join(metricool.REDES)}.\n"
               f"Acompanhe no planejamento do Metricool.", chat)
    except Exception as e:
        print(_ocultar(traceback.format_exc()))
        avisar(f"Não consegui agendar o vídeo #{vid} no Metricool: {_ocultar(e)[:300]}\n"
               f"Para tentar de novo: /publicar {vid}", chat)


def publicar(vid, chat=None):
    """Depois do Aprovar: usa o Metricool se estiver configurado; senão, o YouTube direto."""
    if metricool.configurado():
        publicar_metricool(vid, chat)
    elif youtube.configurado():
        publicar_youtube(vid, chat)


def enviar_para_aprovacao(vid, prog=None, tentativas=4):
    """Sobe a prévia do vídeo para o Telegram com progresso real e novas tentativas se a conexão cair."""
    v = banco.video(vid)
    if prog is None:
        prog = nova_barra(f"📤 Enviando vídeo #{vid}").atualizar
    prog(0, "Preparando o vídeo", True)
    v = garantir_arquivo(vid)
    if NA_NUVEM and Path(v["arquivo"]).stat().st_size < 48e6:
        previa = Path(v["arquivo"])  # internet do servidor é boa: manda o 1080p direto
    else:
        prog(0, "Preparando a prévia para o Telegram", True)
        previa = criar_previa(v["arquivo"])
    tamanho = previa.stat().st_size / 1e6
    ultimo_erro = None
    for t in range(1, tentativas + 1):
        etapa = f"Enviando para o Telegram ({tamanho:.0f} MB)" + (f", tentativa {t} de {tentativas}" if t > 1 else "")
        try:
            with open(previa, "rb") as f:
                campos = {
                    "chat_id": str(TELEGRAM_CHAT_ID), "caption": texto_video(v), "supports_streaming": "true",
                    "width": "1080" if previa == Path(v["arquivo"]) else "720",
                    "height": "1920" if previa == Path(v["arquivo"]) else "1280", "duration": str(int(v["duracao"])),
                    "reply_markup": json.dumps(botoes_decisao(vid)),
                    "video": (previa.name, f, "video/mp4"),
                }
                enc = MultipartEncoder(fields=campos)
                mon = MultipartEncoderMonitor(enc, lambda m: prog(min(99, m.bytes_read / enc.len * 100), etapa))
                r = requests.post(f"{API}/sendVideo", data=mon, headers={"Content-Type": mon.content_type},
                                  timeout=(15, 600)).json()
            if not r.get("ok"):
                raise RuntimeError(f"Telegram recusou: {r.get('description')}")
            break
        except Exception as e:
            ultimo_erro = _ocultar(e)
            print(f"\nEnvio falhou (tentativa {t}): {ultimo_erro[:200]}")
            if t == tentativas:
                raise RuntimeError(f"Não consegui enviar o vídeo #{vid} depois de {tentativas} tentativas. "
                                   f"Verifique a internet e mande /pendentes. Detalhe: {ultimo_erro[:200]}")
            time.sleep(5 * t)
    prog(100, f"Vídeo #{vid} enviado. Aprove logo abaixo 👇", True)
    banco.atualizar_video(vid, status="aguardando", telegram_msg=r["result"]["message_id"])
    nuvem.salvar_estado(f"vídeo {vid} enviado")


def reenviar_pendentes(chat):
    pend = banco.videos_por_status("gerado") + banco.videos_por_status("aguardando")
    if not pend:
        avisar("Nenhum vídeo pendente.", chat)
        return
    for v in pend:
        try:
            enviar_para_aprovacao(v["id"])
        except Exception as e:
            print(_ocultar(traceback.format_exc()))
            avisar(_ocultar(e)[:400], chat)


def gerar_e_enviar(streamer, chat, buscar=True, esperar=False):
    """Monta um vídeo e envia para aprovação. Devolve o número do vídeo, None se faltam clipes,
    ou False se deu erro ou já havia outra montagem em andamento."""
    if not _ocupado.acquire(blocking=esperar):
        avisar("Já estou montando um vídeo, aguarde terminar.", chat)
        return False
    try:
        barra = nova_barra(f"🎬 Clipador · {streamer}", chat)
        if buscar:
            barra.atualizar(0, "Buscando os clipes mais vistos na Twitch", True)
            coletar.coletar()
        vid = montar.gerar_video(streamer, barra.faixa(5, 75))
        if vid is None:
            barra.atualizar(100, f"Não há clipes novos de {streamer} suficientes para passar de 1 minuto.", True)
            return None
        if NA_NUVEM:
            barra.atualizar(76, "Guardando o vídeo em 1080p no GitHub", True)
            banco.atualizar_video(vid, url=nuvem.guardar_video(banco.video(vid)["arquivo"]))
            nuvem.salvar_estado(f"vídeo {vid} montado")
        enviar_para_aprovacao(vid, barra.faixa(80, 100))
        avisar_estoque_baixo()
        return vid
    except Exception as e:  # mantém o bot de pé
        print(_ocultar(traceback.format_exc()))
        avisar(f"Erro: {_ocultar(e)[:400]}", chat)
        return False
    finally:
        _ocupado.release()


def gerar_varios(streamer, chat, quantidade=None):
    """Monta vários vídeos seguidos (quantidade=None: até acabar o estoque de clipes).
    O pedido fica salvo no banco: se o turno acabar no meio, o próximo turno continua."""
    restante = "todos" if quantidade is None else int(quantidade)
    banco.definir_meta("lote", json.dumps({"streamer": streamer, "restante": restante}))
    nuvem.salvar_estado("lote iniciado")
    feitos, erros, primeiro = 0, 0, True
    while restante == "todos" or restante > 0:
        if _fim_do_turno and time.time() > _fim_do_turno - 8 * 60:
            print("Turno acabando: o próximo continua o lote.")
            return
        vid = gerar_e_enviar(streamer, chat, buscar=primeiro, esperar=True)
        primeiro = False
        if vid is None:
            break
        if vid is False:
            erros += 1
            if erros >= 3:
                break
            time.sleep(30)
            continue
        feitos += 1
        if restante != "todos":
            restante -= 1
        banco.definir_meta("lote", json.dumps({"streamer": streamer, "restante": restante}))
        nuvem.salvar_estado(f"lote: vídeo {vid}")
    banco.definir_meta("lote", "")
    nuvem.salvar_estado("lote concluído")
    avisar(f"✅ Lote pronto: {feitos} vídeo(s) de {streamer} enviados para aprovação.\n{texto_estoque()}", chat)


def continuar_lote():
    """Retoma um lote que ficou pela metade no turno anterior."""
    try:
        lote = json.loads(banco.meta("lote", "") or "null")
    except ValueError:
        lote = None
    if lote and lote.get("restante") not in (0, None):
        q = None if lote["restante"] == "todos" else lote["restante"]
        print(f"Retomando lote: {lote}")
        gerar_varios(lote["streamer"], TELEGRAM_CHAT_ID, q)


def decidir(cb):
    chat = cb["message"]["chat"]["id"]
    msg_id = cb["message"]["message_id"]
    acao, _, resto = cb["data"].partition(":")
    vid = int(resto.split(":")[0])
    v = banco.video(vid)
    agora = datetime.now().isoformat(timespec="seconds")
    if v is None:
        return "Vídeo não encontrado"

    if acao == "ap":
        destino = APROVADOS / Path(v["arquivo"]).name
        if Path(v["arquivo"]).exists():
            shutil.move(v["arquivo"], destino)
        banco.atualizar_video(vid, status="aprovado", arquivo=str(destino), decidido_em=agora)
        nuvem.salvar_estado(f"vídeo {vid} aprovado")
        link = f"\n\nArquivo para postar: {v['url']}" if v.get("url") else ""
        chamar("editMessageCaption", chat_id=chat, message_id=msg_id,
               caption=(f"✅ APROVADO{link}\n\n{texto_video(banco.video(vid))}")[:1024])
        threading.Thread(target=publicar, args=(vid, chat), daemon=True).start()
        return "Aprovado"

    if acao == "rp":
        teclas = [[{"text": t, "callback_data": f"mt:{vid}:{k}"}] for k, t in MOTIVOS.items()]
        teclas.append([{"text": "↩️ Voltar", "callback_data": f"vt:{vid}"}])
        chamar("editMessageReplyMarkup", chat_id=chat, message_id=msg_id,
               reply_markup={"inline_keyboard": teclas})
        return "Qual o motivo?"

    if acao == "vt":
        chamar("editMessageReplyMarkup", chat_id=chat, message_id=msg_id, reply_markup=botoes_decisao(vid))
        return ""

    if acao == "mt":
        motivo = resto.split(":")[1]
        banco.atualizar_video(vid, status="reprovado", motivo=motivo, decidido_em=agora)
        if motivo == "corte":  # os clipes voltam para serem usados em outra montagem
            banco.liberar_clipes(vid)
        nuvem.salvar_estado(f"vídeo {vid} reprovado")
        chamar("editMessageCaption", chat_id=chat, message_id=msg_id,
               caption=f"❌ REPROVADO: {MOTIVOS.get(motivo, motivo)}\n\n{texto_video(v)}"[:1024])
        return "Reprovado"

    if acao == "ed":
        banco.definir_meta("legenda_pendente", vid)
        avisar(f"Mande a nova legenda do vídeo #{vid} na próxima mensagem.", chat)
        return ""
    return ""


def tratar_mensagem(m):
    chat = m["chat"]["id"]
    texto = (m.get("text") or "").strip()
    if texto.startswith("/start") and str(chat) == str(TELEGRAM_CHAT_ID):
        avisar("Clipador ligado e configurado ✅\n\n/gerar monta um vídeo agora\n/pendentes reenvia o que falta aprovar\n"
               "/status mostra o resumo", chat)
        return
    if texto.startswith("/start"):
        avisar(f"Clipador ligado. O ID deste chat é {chat}. "
               f"Coloque TELEGRAM_CHAT_ID={chat} no arquivo .env e reinicie o bot.", chat)
        return
    if str(chat) != str(TELEGRAM_CHAT_ID):
        return  # ignora qualquer outro chat
    pendente = banco.meta("legenda_pendente", "")
    if pendente and not texto.startswith("/"):
        vid = int(pendente)
        banco.definir_meta("legenda_pendente", "")
        banco.atualizar_video(vid, legenda=texto)
        nuvem.salvar_estado(f"legenda do vídeo {vid}")
        v = banco.video(vid)
        if v["telegram_msg"]:
            chamar("editMessageCaption", chat_id=chat, message_id=v["telegram_msg"],
                   caption=texto_video(v), reply_markup=botoes_decisao(vid))
        avisar(f"Legenda do vídeo #{vid} atualizada.", chat)
        return
    if texto.startswith("/gerar"):
        partes = texto.split()[1:]
        todos = any(p.lower() == "todos" for p in partes)
        qtd = next((int(p) for p in partes if p.isdigit()), None)
        nomes = [p.lower() for p in partes if p.lower() != "todos" and not p.isdigit()]
        streamer = nomes[0] if nomes else STREAMERS[0]
        if streamer not in STREAMERS:
            avisar(f"{streamer} não está na lista de streamers autorizados ({', '.join(STREAMERS)}).", chat)
            return
        if todos or (qtd and qtd > 1):
            avisar(f"Vou montar {'todos os vídeos que o estoque permite' if todos else f'{qtd} vídeos'} de {streamer}, "
                   "um atrás do outro. Cada um chega aqui para aprovar.", chat)
            threading.Thread(target=gerar_varios, args=(streamer, chat, None if todos else qtd), daemon=True).start()
        else:
            threading.Thread(target=gerar_e_enviar, args=(streamer, chat), daemon=True).start()
    elif texto.startswith("/publicar"):
        partes = texto.split()
        if len(partes) > 1 and partes[1].isdigit():
            vid = int(partes[1])
            if banco.video(vid) and (banco.video(vid).get("youtube") or "").startswith("metricool:"):
                banco.atualizar_video(vid, youtube=None)  # tentar de novo
            threading.Thread(target=publicar, args=(vid, chat), daemon=True).start()
        else:
            avisar("Use assim: /publicar 3 (o número do vídeo).", chat)
    elif texto.startswith("/pendentes"):
        threading.Thread(target=reenviar_pendentes, args=(chat,), daemon=True).start()
    elif texto.startswith("/status"):
        c = {s: len(banco.videos_por_status(s)) for s in ("aguardando", "aprovado", "reprovado")}
        avisar(texto_estoque(), chat)
        auto = (f"ligada ({', '.join(HORARIOS)})" if _auto_ligado() and HORARIOS else "desligada")
        avisar(f"Aguardando: {c['aguardando']}\nAprovados: {c['aprovado']}\nReprovados: {c['reprovado']}\n"
               f"Geração automática: {auto}", chat)
    elif texto.startswith("/pausar"):
        banco.definir_meta("auto_pausado", "1")
        nuvem.salvar_estado("pausado")
        avisar("Geração automática pausada. Mande /retomar para voltar.", chat)
    elif texto.startswith("/retomar"):
        banco.definir_meta("auto_pausado", "0")
        nuvem.salvar_estado("retomado")
        avisar(f"Geração automática ligada: {', '.join(HORARIOS) or 'nenhum horário no .env'}.", chat)


def texto_estoque():
    """Quantos clipes ainda não usados existem e para quantos vídeos eles dão."""
    linhas = []
    for st in STREAMERS:
        livres = [c for c in banco.clipes_livres(st) if c["duracao"] >= montar.CLIPE_MIN]
        seg = sum(c["duracao"] for c in livres)
        novos = sum(1 for c in livres if c["data"] >= (datetime.now().strftime("%Y%m%d")))
        linhas.append(f"📦 {st}: {len(livres)} clipes livres (~{int(seg // 75)} vídeos), {novos} de hoje")
    return "\n".join(linhas)


def avisar_estoque_baixo():
    for st in STREAMERS:
        livres = [c for c in banco.clipes_livres(st) if c["duracao"] >= montar.CLIPE_MIN]
        videos = int(sum(c["duracao"] for c in livres) // 75)
        if videos <= 4 and banco.meta(f"aviso_estoque_{st}") != datetime.now().strftime("%Y-%m-%d"):
            banco.definir_meta(f"aviso_estoque_{st}", datetime.now().strftime("%Y-%m-%d"))
            avisar(f"⚠️ Estoque baixo de {st}: só dá para uns {videos} vídeos. "
                   f"Os clipes novos das lives entram sozinhos; se quiser, adicione outro streamer.")


def _horario_devido(agora):
    """Devolve o horário de hoje que já passou (há menos de 3 h) e ainda não foi feito."""
    feitos = json.loads(banco.meta("horarios_feitos", "[]"))
    for h in HORARIOS:
        try:
            hh, mm = (int(x) for x in h.split(":"))
        except ValueError:
            continue
        alvo = agora.replace(hour=hh, minute=mm, second=0, microsecond=0)
        chave = alvo.strftime("%Y-%m-%d %H:%M")
        if 0 <= (agora - alvo).total_seconds() < 3 * 3600 and chave not in feitos:
            return chave, feitos
    return None, feitos


def agendador():
    """Nos horários do .env, monta POR_HORARIO vídeos e envia (um streamer por vez, em rodízio).
    Se o bot estava desligado na hora certa, faz assim que ligar (até 3 h depois)."""
    while True:
        try:
            chave, feitos = _horario_devido(datetime.now())
            if chave and _auto_ligado():
                banco.definir_meta("horarios_feitos", json.dumps((feitos + [chave])[-20:]))
                n = int(banco.meta("proximo_streamer", "0"))
                banco.definir_meta("proximo_streamer", n + 1)
                streamer = STREAMERS[n % len(STREAMERS)]
                print(f"[{chave}] geração automática: {POR_HORARIO} vídeo(s) de {streamer}")
                if banco.meta("lote", ""):
                    print("Já há um lote em andamento; ele cobre este horário.")
                elif POR_HORARIO > 1:
                    gerar_varios(streamer, TELEGRAM_CHAT_ID, POR_HORARIO)
                else:
                    gerar_e_enviar(streamer, TELEGRAM_CHAT_ID)
        except Exception:
            print(_ocultar(traceback.format_exc()))
        time.sleep(20)


def _uma_instancia():
    """Impede dois bots ao mesmo tempo (o Telegram recusa e os botões param de funcionar)."""
    import socket
    trava = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        trava.bind(("127.0.0.1", 47913))
    except OSError:
        print("O Clipador já está ligado em outra janela ou em segundo plano.")
        raise SystemExit(3)
    return trava


def rodar_bot():
    _trava = _uma_instancia()  # noqa: F841 (fica aberta enquanto o bot roda)
    if not TELEGRAM_TOKEN:
        raise SystemExit("Falta TELEGRAM_TOKEN (no .env, ou nos Secrets do GitHub).")
    nuvem.restaurar_estado()
    global _fim_do_turno
    fim = time.time() + MAX_MINUTOS * 60 if MAX_MINUTOS else None
    _fim_do_turno = fim
    chamar("setMyCommands", commands=[
        {"command": "gerar", "description": "Montar um vídeo (ou: /gerar todos, /gerar 5)"},
        {"command": "pendentes", "description": "Reenviar vídeos ainda não decididos"},
        {"command": "status", "description": "Resumo de aprovados e reprovados"},
        {"command": "pausar", "description": "Pausar a geração automática"},
        {"command": "retomar", "description": "Retomar a geração automática"},
    ])
    if TELEGRAM_CHAT_ID and os.getenv("CLIPADOR_GERAR_TODOS", "").lower() == "true" and not banco.meta("lote", ""):
        banco.definir_meta("lote", json.dumps({"streamer": STREAMERS[0], "restante": "todos"}))
    if TELEGRAM_CHAT_ID:
        threading.Thread(target=continuar_lote, daemon=True).start()
    if TELEGRAM_CHAT_ID and HORARIOS:
        threading.Thread(target=agendador, daemon=True).start()
        print(f"Geração automática nos horários: {', '.join(HORARIOS)}")
    print("Bot rodando. Ctrl+C para parar.")
    offset = 0
    while True:
        if fim and time.time() > fim and not _ocupado.locked():
            break
        try:
            r = requests.get(f"{API}/getUpdates", params={"offset": offset, "timeout": 50}, timeout=60).json()
            for u in r.get("result", []):
                offset = u["update_id"] + 1
                try:
                    if "callback_query" in u:
                        cb = u["callback_query"]
                        if str(cb["message"]["chat"]["id"]) != str(TELEGRAM_CHAT_ID):
                            continue
                        aviso = decidir(cb)
                        chamar("answerCallbackQuery", callback_query_id=cb["id"], text=aviso)
                    elif "message" in u:
                        tratar_mensagem(u["message"])
                except Exception:
                    print(_ocultar(traceback.format_exc()))
        except requests.RequestException:
            time.sleep(5)
    # Fim do turno na nuvem: confirma as mensagens lidas e salva o estado para a próxima execução
    try:
        requests.get(f"{API}/getUpdates", params={"offset": offset, "timeout": 0}, timeout=20)
    except requests.RequestException:
        pass
    nuvem.salvar_estado("fim do turno")
    print("Turno encerrado; a próxima execução continua de onde parou.")


if __name__ == "__main__":
    rodar_bot()
