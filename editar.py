"""Acabamento "editado" para o vídeo final (pedido do Rodrigo em 24/11, por causa do TikTok):

- cortes mais rápidos: tira os silêncios e pausas (> 0,5 s) do meio dos clipes;
- título forte nos primeiros segundos;
- legenda falada na tela, 2 a 3 palavras por vez (transcrição local com faster-whisper).

Mantém o padrão (facecam em cima, jogo embaixo) e a tela final com o @ do vídeo original.
Uso: python editar.py entrada.mp4 saida.mp4 "Título do gancho"
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from config import BASE, TELA_FINAL_SEG

FONTE_DIR = "assets"
FONTE_NOME = "Inter Display"
SILENCIO_DB = -30
SILENCIO_MIN = 0.5
FOLGA = 0.12
GANCHO_SEG = 3.0
VIDEO = ["-c:v", "libx264", "-preset", "medium", "-crf", "21", "-maxrate", "3800k", "-bufsize", "7600k",
         "-pix_fmt", "yuv420p", "-r", "30"]
AUDIO = ["-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2"]
_modelo = None


def _rodar(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=BASE)
    if r.returncode != 0:
        raise RuntimeError(f"Falhou: {' '.join(map(str, cmd[:4]))}...\n{r.stderr[-1500:]}")
    return r.stdout + r.stderr


def _duracao(arq):
    return float(_rodar(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(arq)]).split()[0])


def trechos_com_som(arq, fim):
    """Partes do vídeo (até `fim`) sem os silêncios longos."""
    saida = _rodar(["ffmpeg", "-hide_banner", "-t", f"{fim:.3f}", "-i", str(arq), "-af",
                    f"silencedetect=noise={SILENCIO_DB}dB:d={SILENCIO_MIN}", "-f", "null", "-"])
    inicios = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", saida)]
    finais = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", saida)]
    trechos, pos = [], 0.0
    for i, ini in enumerate(inicios):
        fim_sil = finais[i] if i < len(finais) else fim
        if ini - pos > 0.05:
            trechos.append((pos, min(fim, ini + FOLGA)))
        pos = max(pos, fim_sil - FOLGA)
    if fim - pos > 0.05:
        trechos.append((pos, fim))
    return [(a, b) for a, b in trechos if b - a > 0.25] or [(0.0, fim)]


def _modelo_whisper():
    global _modelo
    if _modelo is None:
        from faster_whisper import WhisperModel
        _modelo = WhisperModel("small", device="cpu", compute_type="int8")
    return _modelo


def _audio16k(arq):
    import numpy as np
    bruto = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(arq), "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
                           capture_output=True, check=True, cwd=BASE).stdout
    return np.frombuffer(bruto, np.int16).astype(np.float32) / 32768.0


def palavras(arq):
    segs, _ = _modelo_whisper().transcribe(_audio16k(arq), language="pt", word_timestamps=True, vad_filter=True)
    return [(w.start, w.end, w.word.strip()) for s in segs for w in (s.words or []) if w.word.strip()]


def _t(seg):
    h, r = divmod(max(0, seg), 3600)
    m, s = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _limpa(txt):
    return txt.replace("{", "(").replace("}", ")").replace("\\", "")


def _quebrar(txt, largura=16):
    linhas, atual = [], ""
    for p in txt.split():
        if atual and len(atual) + 1 + len(p) > largura:
            linhas.append(atual)
            atual = p
        else:
            atual = f"{atual} {p}".strip()
    if atual:
        linhas.append(atual)
    return "\\N".join(linhas[:3])


def legenda_ass(lista, gancho, dur):
    estilos = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 2\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Fala,{FONTE_NOME},84,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,7,3,2,60,60,470,1\n"
        f"Style: Gancho,{FONTE_NOME},76,&H00000000,&H00000000,&H0000E5FF,&H0000E5FF,-1,0,0,0,100,100,0,0,3,18,0,8,70,70,740,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    ev = []
    if gancho:
        ev.append(f"Dialogue: 1,{_t(0)},{_t(min(GANCHO_SEG, dur))},Gancho,,0,0,0,,"
                  f"{{\\fad(0,200)\\t(0,150,\\fscx108\\fscy108)\\t(150,300,\\fscx100\\fscy100)}}"
                  f"{_quebrar(_limpa(gancho.upper()))}")
    grupo = []
    for i, (ini, fim, w) in enumerate(lista):
        grupo.append((ini, fim, w))
        prox = lista[i + 1][0] if i + 1 < len(lista) else None
        if len(grupo) == 3 or prox is None or prox - fim > 0.35 or w[-1:] in ".?!,":
            a = grupo[0][0]
            b = min(prox, grupo[-1][1] + 0.25) if prox else grupo[-1][1] + 0.25
            if gancho and a < GANCHO_SEG:  # durante o gancho a fala desce um pouco para não brigar
                pass
            txt = _limpa(" ".join(x[2] for x in grupo).upper())
            ev.append(f"Dialogue: 0,{_t(a)},{_t(b)},Fala,,0,0,0,,{{\\fscx90\\fscy90\\t(0,90,\\fscx100\\fscy100)}}{txt}")
            grupo = []
    return estilos + "\n".join(ev) + "\n"


def editar(entrada, saida, gancho="", com_legenda=True):
    entrada, saida = Path(entrada), Path(saida)
    total = _duracao(entrada)
    fim_conteudo = max(1.0, total - TELA_FINAL_SEG)
    trechos = trechos_com_som(entrada, fim_conteudo)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # 1) corta as pausas
        sel = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in trechos)
        cortado = tmp / "cortado.mp4"
        _rodar(["ffmpeg", "-y", "-loglevel", "error", "-t", f"{fim_conteudo:.3f}", "-i", str(entrada),
                "-vf", f"select='{sel}',setpts=N/FRAME_RATE/TB", "-af", f"aselect='{sel}',asetpts=N/SR/TB",
                *VIDEO, *AUDIO, str(cortado)])
        dur = _duracao(cortado)
        # 2) legenda e gancho
        lista = palavras(cortado) if com_legenda else []
        ass = tmp / "legenda.ass"
        ass.write_text(legenda_ass(lista, gancho, dur), encoding="utf-8")
        legendado = tmp / "legendado.mp4"
        filtro = f"subtitles=filename='{ass.as_posix()}':fontsdir='{FONTE_DIR}'"
        _rodar(["ffmpeg", "-y", "-loglevel", "error", "-i", str(cortado), "-vf", filtro, *VIDEO, "-c:a", "copy",
                str(legendado)])
        # 3) devolve a tela final com o @
        final = tmp / "final.mp4"
        _rodar(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{fim_conteudo:.3f}", "-i", str(entrada),
                *VIDEO, *AUDIO, str(final)])
        lista_concat = tmp / "lista.txt"
        lista_concat.write_text(f"file '{legendado.as_posix()}'\nfile '{final.as_posix()}'\n")
        _rodar(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lista_concat),
                "-c", "copy", "-movflags", "+faststart", str(saida)])
    return {"antes": round(total, 1), "depois": round(_duracao(saida), 1), "cortes": len(trechos) - 1,
            "palavras": len(lista)}


if __name__ == "__main__":
    print(editar(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else ""))
