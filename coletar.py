"""Coleta: lista os clipes mais vistos de cada streamer na Twitch."""
import json
import subprocess

import banco
from config import CLIPES_POR_BUSCA, PERIODOS, STREAMERS


def listar_clipes(streamer, periodo, limite=CLIPES_POR_BUSCA):
    url = f"https://www.twitch.tv/{streamer}/clips?range={periodo}"
    saida = subprocess.run(
        ["yt-dlp", "-J", "--playlist-end", str(limite), url],
        capture_output=True, text=True, check=True,
    ).stdout
    dados = json.loads(saida)
    clipes = []
    for e in dados.get("entries") or []:
        if not e:
            continue
        clipes.append({
            "id": str(e["id"]),
            "streamer": streamer,
            "titulo": e.get("title") or "",
            "url": e.get("webpage_url"),
            "duracao": float(e.get("duration") or 0),
            "views": int(e.get("view_count") or 0),
            "data": e.get("upload_date") or "",
        })
    return clipes


def coletar():
    total = 0
    for s in STREAMERS:
        for periodo in PERIODOS:
            clipes = listar_clipes(s, periodo)
            banco.salvar_clipes(clipes)
            total += len(clipes)
            print(f"{s} ({periodo}): {len(clipes)} clipes")
    return total


if __name__ == "__main__":
    coletar()
