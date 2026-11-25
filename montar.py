"""Montagem: escolhe clipes, baixa, monta no padrão 9:16 e junta num vídeo só.

Padrão: facecam no topo (1080x640), gameplay embaixo (1080x1280),
crédito do streamer e tela final com o nosso @.
"""
import json
import subprocess
import tempfile
from pathlib import Path

import re

import cv2

import banco
from progresso import SemProgresso
from config import (BASE, BRUTOS, CLIPE_MIN, DURACAO_MAX, DURACAO_MIN, FACECAM_SO_NO_CANTO, FONTE,
                    NOSSO_ARROBA, PRONTOS, TELA_FINAL_SEG)

LARG, ALT = 1080, 1920
CAM_ALT = 640
JOGO_ALT = ALT - CAM_ALT
FPS = 30
VIDEO_OPTS = ["-c:v", "libx264", "-preset", "medium", "-crf", "21",
              "-maxrate", "3800k", "-bufsize", "7600k", "-pix_fmt", "yuv420p", "-r", str(FPS)]
AUDIO_OPTS = ["-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2"]


def rodar(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=BASE)
    if r.returncode != 0:
        raise RuntimeError(f"Falhou: {' '.join(cmd[:4])}...\n{r.stderr[-1500:]}")
    return r.stdout


def rodar_ffmpeg(cmd, dur, prog, etapa):
    """Roda o FFmpeg lendo o progresso real (tempo já processado / duração)."""
    cmd = [cmd[0], "-progress", "pipe:1", "-nostats", *cmd[1:]]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=BASE)
    for linha in p.stdout:
        if linha.startswith("out_time_us=") and dur:
            try:
                feito = int(linha.split("=")[1]) / 1e6
                prog(min(100, feito / dur * 100), etapa)
            except ValueError:
                pass
    err = p.stderr.read()
    if p.wait() != 0:
        raise RuntimeError(f"FFmpeg falhou:\n{err[-1500:]}")


def duracao(arquivo):
    return float(rodar(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(arquivo)]).strip())


# ---------- 1. escolher clipes ----------

def escolher_clipes(streamer):
    """Pega os clipes livres mais vistos até a soma ficar entre DURACAO_MIN e DURACAO_MAX."""
    escolhidos, total = [], 0.0
    for c in banco.clipes_livres(streamer):
        if c["duracao"] < CLIPE_MIN or total + c["duracao"] > DURACAO_MAX:
            continue
        escolhidos.append(c)
        total += c["duracao"]
        if total >= DURACAO_MIN:
            break
    if total < DURACAO_MIN:
        return None
    # Mais forte primeiro, segundo mais forte por último
    if len(escolhidos) > 2:
        escolhidos = [escolhidos[0]] + escolhidos[2:] + [escolhidos[1]]
    return escolhidos


# ---------- 2. baixar ----------

def baixar(clipe, prog=None, etapa="Baixando"):
    destino = BRUTOS / f"{clipe['id']}.mp4"
    if destino.exists():
        return destino
    cmd = ["yt-dlp", "-q", "--progress", "--newline",
           "--progress-template", "download:PCT %(progress._percent_str)s",
           "-f", "best[height<=1080]", "--merge-output-format", "mp4", "-o", str(destino), clipe["url"]]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=BASE)
    for linha in p.stdout:
        m = re.search(r"PCT\s+([\d.]+)%", linha)
        if m and prog:
            prog(float(m.group(1)), etapa)
    err = p.stderr.read()
    if p.wait() != 0:
        raise RuntimeError(f"Download falhou:\n{err[-800:]}")
    return destino


# ---------- 3. achar a facecam ----------

_detector = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


def detectar_rosto(arquivo, amostras=8):
    """Procura o rosto do streamer em vários quadros e devolve a posição mais frequente."""
    cap = cv2.VideoCapture(str(arquivo))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    escala = 960 / w
    achados = []
    for i in range(amostras):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(n * (i + 0.5) / amostras))
        ok, quadro = cap.read()
        if not ok:
            continue
        cinza = cv2.cvtColor(cv2.resize(quadro, None, fx=escala, fy=escala), cv2.COLOR_BGR2GRAY)
        rostos = _detector.detectMultiScale(cinza, 1.1, 6, minSize=(30, 30), maxSize=(170, 170))
        for (x, y, fw, fh) in rostos:
            achados.append((x / escala, y / escala, fw / escala, fh / escala))
    cap.release()
    if not achados:
        return None
    # Agrupa por posição e fica com o grupo que aparece em mais quadros (a webcam é fixa)
    grupos = []
    for a in achados:
        cx, cy = a[0] + a[2] / 2, a[1] + a[3] / 2
        for g in grupos:
            gx, gy = g[0][0] + g[0][2] / 2, g[0][1] + g[0][3] / 2
            if abs(cx - gx) < 80 and abs(cy - gy) < 80:
                g.append(a)
                break
        else:
            grupos.append([a])
    melhor = max(grupos, key=len)
    if len(melhor) < 2:
        return None
    med = lambda k: sorted(a[k] for a in melhor)[len(melhor) // 2]
    return (med(0), med(1), med(2), med(3))


def rosto_no_canto(rosto, w):
    """Webcam sobreposta fica na borda; rosto no meio do quadro é gente na cena (live IRL)."""
    cx = rosto[0] + rosto[2] / 2
    return cx < w * 0.3 or cx > w * 0.7


def recorte_cam(rosto, w, h):
    """Retângulo da facecam em volta do rosto, na proporção da faixa de cima."""
    x, y, fw, fh = rosto
    cw = min(fw * 3.4, w)
    ch = cw * CAM_ALT / LARG
    cx, cy = x + fw / 2, y + fh / 2
    x0 = min(max(cx - cw / 2, 0), w - cw)
    y0 = min(max(cy - ch * 0.45, 0), h - ch)
    return int(x0), int(y0), int(cw) // 2 * 2, int(ch) // 2 * 2


def recorte_jogo(cam, w, h):
    """Faixa central do gameplay; desvia da facecam quando ela está no meio."""
    jw = int(h * LARG / JOGO_ALT) // 2 * 2
    x0 = (w - jw) // 2
    if cam:
        cx0, _, cw, _ = cam
        if cx0 < x0 + jw and cx0 + cw > x0:  # sobrepõe
            esquerda = cx0 - jw
            direita = cx0 + cw
            x0 = esquerda if esquerda >= 0 and cx0 > w - (cx0 + cw) else min(direita, w - jw)
            x0 = max(0, min(x0, w - jw))
    return x0, 0, jw, h


# ---------- 4. montar cada clipe no padrão ----------

def _texto(t):
    return t.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’")


def montar_clipe(bruto, streamer, saida, prog=None, etapa="Montando"):
    cap = cv2.VideoCapture(str(bruto))
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    rosto = detectar_rosto(bruto)
    if rosto and streamer in FACECAM_SO_NO_CANTO and not rosto_no_canto(rosto, w):
        rosto = None
    credito = (f"drawtext=fontfile='{FONTE}':text='{_texto('twitch.tv/' + streamer)}':"
               f"fontsize=38:fontcolor=white:box=1:boxcolor=black@0.55:boxborderw=12:x=(w-text_w)/2:y={CAM_ALT + 24}")
    if rosto:
        cam = recorte_cam(rosto, w, h)
        jx, jy, jw, jh = recorte_jogo(cam, w, h)
        cx, cy, cw, ch = cam
        filtro = (
            f"[0:v]split=2[a][b];"
            f"[a]crop={cw}:{ch}:{cx}:{cy},scale={LARG}:{CAM_ALT}[cam];"
            f"[b]crop={jw}:{jh}:{jx}:{jy},scale={LARG}:{JOGO_ALT}[jogo];"
            f"[cam][jogo]vstack,drawbox=x=0:y={CAM_ALT - 3}:w={LARG}:h=6:color=black@0.9:t=fill,"
            f"{credito},setsar=1,fps={FPS}[v]"
        )
        layout = "facecam"
    else:
        # Sem webcam visível: quadro inteiro no meio, fundo desfocado
        filtro = (
            f"[0:v]split=2[a][b];"
            f"[a]scale=-2:{ALT},crop={LARG}:{ALT},boxblur=30:3,eq=brightness=-0.15[fundo];"
            f"[b]scale={LARG}:-2[meio];"
            f"[fundo][meio]overlay=0:(H-h)/2,"
            f"{credito.replace(f'y={CAM_ALT + 24}', 'y=(h/2)-(1080*h/1920/2)-70')},setsar=1,fps={FPS}[v]"
        )
        layout = "sem facecam"
    rodar_ffmpeg(["ffmpeg", "-y", "-loglevel", "error", "-i", str(bruto), "-filter_complex", filtro,
                  "-map", "[v]", "-map", "0:a?", *VIDEO_OPTS, *AUDIO_OPTS, str(saida)],
                 duracao(bruto), prog or (lambda *a: None), etapa)
    return layout


def tela_final(saida):
    t1 = (f"drawtext=fontfile='{FONTE}':text='{_texto(NOSSO_ARROBA)}':fontsize=110:fontcolor=white:"
          f"x=(w-text_w)/2:y=(h-text_h)/2-40")
    t2 = (f"drawtext=fontfile='{FONTE}':text='Siga para mais clipes':fontsize=48:fontcolor=white@0.8:"
          f"x=(w-text_w)/2:y=(h/2)+70")
    rodar(["ffmpeg", "-y", "-loglevel", "error",
           "-f", "lavfi", "-i", f"color=c=0x111111:s={LARG}x{ALT}:d={TELA_FINAL_SEG}:r={FPS}",
           "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo",
           "-vf", f"{t1},{t2},fade=t=in:st=0:d=0.3", "-t", str(TELA_FINAL_SEG),
           *VIDEO_OPTS, *AUDIO_OPTS, "-shortest", str(saida)])


def _garantir_audio(arquivo, tmp):
    """Clipes sem trilha de áudio quebram a junção; adiciona silêncio."""
    tem = rodar(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                 "-of", "csv=p=0", str(arquivo)]).strip()
    if tem:
        return arquivo
    novo = Path(tmp) / f"a_{arquivo.name}"
    rodar(["ffmpeg", "-y", "-loglevel", "error", "-i", str(arquivo), "-f", "lavfi",
           "-i", "anullsrc=r=48000:cl=stereo", "-shortest", "-c:v", "copy", *AUDIO_OPTS, str(novo)])
    return novo


# ---------- 5. tudo junto ----------

def legenda_sugerida(streamer, clipes):
    titulos = " | ".join(c["titulo"] for c in clipes[:3])
    return (f"{titulos}\n\nClipes de twitch.tv/{streamer}\n"
            f"#{streamer} #twitch #clipes #shorts")


def gerar_video(streamer, prog=None):
    """prog: função(pct 0–100, etapa) para mostrar a barra de progresso."""
    prog = prog or SemProgresso().atualizar
    clipes = escolher_clipes(streamer)
    if not clipes:
        print(f"{streamer}: clipes livres insuficientes para passar de {DURACAO_MIN}s")
        return None
    n = len(clipes)
    fatia = 90 / n  # 0–90% para os clipes, 90–100% para tela final e junção
    with tempfile.TemporaryDirectory() as tmp:
        partes, layouts = [], []
        for i, c in enumerate(clipes):
            ini = i * fatia
            baixar(c, lambda p, e: prog(ini + fatia * 0.3 * p / 100, e),
                   f"Baixando clipe {i + 1} de {n}")
            prog(ini + fatia * 0.3, f"Montando clipe {i + 1} de {n} no 9:16")
            parte = Path(tmp) / f"{i:02d}.mp4"
            layouts.append(montar_clipe(BRUTOS / f"{c['id']}.mp4", streamer, parte,
                                        lambda p, e: prog(ini + fatia * (0.3 + 0.7 * p / 100), e),
                                        f"Montando clipe {i + 1} de {n} no 9:16"))
            partes.append(_garantir_audio(parte, tmp))
        prog(92, "Criando a tela final com o @")
        fim = Path(tmp) / "fim.mp4"
        tela_final(fim)
        prog(96, "Juntando os clipes")
        partes.append(fim)
        lista = Path(tmp) / "lista.txt"
        lista.write_text("".join(f"file '{Path(p).as_posix()}'\n" for p in partes))
        nome = f"{streamer}_{'-'.join(c['id'][:6] for c in clipes)}.mp4"
        saida = PRONTOS / nome
        rodar(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lista),
               "-c", "copy", "-movflags", "+faststart", str(saida)])
    dur = duracao(saida)
    vid = banco.criar_video(streamer, clipes, saida, dur, legenda_sugerida(streamer, clipes))
    prog(100, f"Vídeo #{vid} pronto ({dur:.0f}s)")
    print(f"Vídeo {vid}: {saida.name} ({dur:.0f}s, {len(clipes)} clipes, layouts: {', '.join(layouts)})")
    return vid


if __name__ == "__main__":
    import sys
    from config import STREAMERS
    from progresso import Progresso
    gerar_video(sys.argv[1] if len(sys.argv) > 1 else STREAMERS[0], Progresso("Montando").atualizar)
