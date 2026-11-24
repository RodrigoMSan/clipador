"""Posta o próximo vídeo aprovado no YouTube e, com META_TOKEN, nos Reels do Instagram e do Facebook,
sem o bot ligado (usado quando o Actions está fora).

Lê o estado do ramo `estado`, escolhe o próximo aprovado (clipes dos últimos 3 dias primeiro,
depois o portfólio por número), baixa o 1080p das Releases, envia ao YouTube, grava o link no
banco (coluna youtube) e salva o estado de volta no ramo `estado`.

Precisa de YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET e YOUTUBE_REFRESH_TOKEN no ambiente.
Antes de enviar, aplica o acabamento "editado" (editar.py): corta pausas, gancho e legenda na tela.

Uso:
  python postar_youtube.py --proximo                 mostra o próximo vídeo da fila (para escrever o gancho)
  python postar_youtube.py --gancho "TEXTO" [--video N]   edita e posta (YouTube, Instagram, Facebook)
  python postar_youtube.py --so-editar N --gancho "TEXTO"  só edita e devolve um link público (TikTok)
  python postar_youtube.py --teste                   só confere as autorizações
"""
import json
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import requests

import meta
import midia
import youtube

REPO = "https://github.com/RodrigoMSan/clipador"
BASE = Path(__file__).resolve().parent


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True)


def ja_publicados():
    arq = BASE / "ja_publicados.txt"
    return {int(x) for x in arq.read_text().split() if x.isdigit()} if arq.exists() else set()


def escolher(con):
    limite = (datetime.now() - timedelta(days=3)).strftime("%Y%m%d")
    fora = ja_publicados()
    melhor = None
    for v in con.execute("SELECT * FROM videos WHERE status='aprovado' AND (youtube IS NULL OR youtube='') ORDER BY id"):
        if v["id"] in fora:
            continue
        ids = json.loads(v["clipes"] or "[]")
        clipes = [dict(r) for r in con.execute(
            f"SELECT titulo, data, views FROM clipes WHERE id IN ({','.join('?' * len(ids))})", ids)] if ids else []
        novo = max((c["data"] or "" for c in clipes), default="")
        chave = (0, -int(novo or 0), v["id"]) if novo >= limite else (1, 0, v["id"])
        if melhor is None or chave < melhor[0]:
            melhor = (chave, dict(v), clipes)
    return melhor


def _arg(nome):
    if nome in sys.argv:
        i = sys.argv.index(nome)
        return sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
    return None


def _baixar(url, destino):
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(destino, "wb") as f:
            for pedaco in r.iter_content(1 << 20):
                f.write(pedaco)


def _editar(arquivo, gancho):
    """Devolve o arquivo editado; se a edição falhar, segue com o original."""
    try:
        import editar
        saida = arquivo.with_name(arquivo.stem + "_editado.mp4")
        info = editar.editar(arquivo, saida, gancho)
        print(f"Edição: {info}")
        return saida, True
    except Exception as e:
        print(f"Edição falhou, usando o original: {e}")
        return arquivo, False


def _clipes(con, v):
    ids = json.loads(v["clipes"] or "[]")
    return [dict(r) for r in con.execute(
        f"SELECT titulo, data, views FROM clipes WHERE id IN ({','.join('?' * len(ids))})", ids)] if ids else []


def main():
    if not youtube.configurado():
        sys.exit("Faltam YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET e YOUTUBE_REFRESH_TOKEN no ambiente.")
    if "--teste" in sys.argv:
        tok = youtube._token_de_acesso()
        info = requests.get("https://oauth2.googleapis.com/tokeninfo", params={"access_token": tok}, timeout=30).json()
        print("YouTube OK. Escopo:", info.get("scope"))
        if meta.configurado():
            pagina, _, ig = meta.contas()
            print("Meta OK. Página:", pagina, "Instagram:", ig)
        return
    pasta = Path(tempfile.mkdtemp())
    git("clone", "-q", "--depth", "1", "-b", "estado", REPO, str(pasta / "estado"), cwd=pasta)
    db = pasta / "estado" / "clipador.db"
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    gancho = (_arg("--gancho") or "").strip()
    so_editar = _arg("--so-editar")
    forcado = _arg("--video") or so_editar
    if forcado:
        linha = con.execute("SELECT * FROM videos WHERE id=?", (int(forcado),)).fetchone()
        if not linha:
            sys.exit(f"Vídeo {forcado} não existe.")
        v = dict(linha)
        clipes = _clipes(con, v)
    else:
        escolha = escolher(con)
        if not escolha:
            print("FILA_VAZIA: não há vídeo aprovado para postar.")
            return
        _, v, clipes = escolha
    if "--proximo" in sys.argv:
        print(f"PROXIMO: vídeo {v['id']}")
        for c in sorted(clipes, key=lambda c: -(c["views"] or 0)):
            print(f"  clipe ({c['data']}, {c['views']} views): {c['titulo']}")
        print(f"  legenda: {v['legenda']!r}")
        return
    if not v.get("url"):
        sys.exit(f"O vídeo {v['id']} não tem link público.")
    original = pasta / f"video_{v['id']}.mp4"
    _baixar(v["url"], original)
    arquivo, editado = _editar(original, gancho)
    if so_editar:
        url = midia.publicar_arquivo(arquivo, f"video_{v['id']}_editado.mp4") if editado else v["url"]
        print(f"LINK: {url}")
        return
    url_publica = midia.publicar_arquivo(arquivo, f"video_{v['id']}_editado.mp4") if editado else v["url"]
    # título: o clipe mais visto cujo título é legível (pelo menos 8 letras/números)
    por_views = sorted(clipes, key=lambda c: -(c["views"] or 0))
    legiveis = [c for c in por_views if sum(ch.isalnum() for ch in (c["titulo"] or "")) >= 8]
    clipes_ordenados = (legiveis or por_views)[:1]
    titulo, descricao = youtube.titulo_e_descricao(v, clipes_ordenados)
    if gancho:
        titulo = f"{gancho[:100 - len(' | ' + v['streamer'] + ' #shorts')]} | {v['streamer']} #shorts"
    colunas = {r[1] for r in con.execute("PRAGMA table_info(videos)")}
    for col in ("instagram", "facebook"):
        if col not in colunas:
            con.execute(f"ALTER TABLE videos ADD COLUMN {col} TEXT")
    resultado = []
    try:
        link, privacidade = youtube.publicar(str(arquivo), titulo, descricao,
                                             tags=[v["streamer"], "twitch", "clipes", "shorts"])
        con.execute("UPDATE videos SET youtube=? WHERE id=?", (link, v["id"]))
        resultado.append(f"YouTube {link} ({privacidade})")
    except Exception as e:
        con.execute("UPDATE videos SET youtube=? WHERE id=?", (f"erro: {str(e)[:200]}", v["id"]))
        resultado.append(f"YouTube ERRO: {e}")
    con.commit()
    if meta.configurado():
        legenda = (f"{gancho}\n\n" if gancho else "") + (v["legenda"] or titulo)
        for rede, funcao in (("instagram", meta.instagram), ("facebook", meta.facebook)):
            try:
                link_rede = funcao(url_publica, legenda)
                con.execute(f"UPDATE videos SET {rede}=? WHERE id=?", (link_rede, v["id"]))
                resultado.append(f"{rede.capitalize()} {link_rede}")
            except Exception as e:
                resultado.append(f"{rede.capitalize()} ERRO: {e}")
            con.commit()
    con.close()
    git("add", "clipador.db", cwd=pasta / "estado")
    git("-c", "user.name=Clipador", "-c", "user.email=clipador@users.noreply.github.com",
        "commit", "-q", "-m", f"vídeo {v['id']} no YouTube", cwd=pasta / "estado")
    git("push", "-q", "origin", "estado", cwd=pasta / "estado")
    print(f"POSTADO: vídeo {v['id']} | {titulo} | " + " | ".join(resultado))


if __name__ == "__main__":
    main()
