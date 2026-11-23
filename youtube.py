"""Publicação no YouTube (Shorts) pela API oficial, sem senha: usa uma autorização (refresh token).

Variáveis (Secrets do GitHub ou .env):
  YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN
  YOUTUBE_PRIVACIDADE  public | unlisted | private  (padrão: public)
"""
import json
import os
from pathlib import Path

import requests

CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET", "")
REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN", "")
PRIVACIDADE = os.getenv("YOUTUBE_PRIVACIDADE", "public")
CATEGORIA_JOGOS = "20"


def configurado():
    return bool(CLIENT_ID and CLIENT_SECRET and REFRESH_TOKEN)


def _token_de_acesso():
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN, "grant_type": "refresh_token",
    }, timeout=30)
    dados = r.json()
    if "access_token" not in dados:
        raise RuntimeError(f"YouTube recusou a autorização: {dados.get('error_description') or dados.get('error')}")
    return dados["access_token"]


def titulo_e_descricao(video, clipes):
    """Título curto (até 100 caracteres) com #shorts; a legenda vira a descrição."""
    base = (clipes[0]["titulo"] if clipes else "") or f"Melhores momentos de {video['streamer']}"
    titulo = f"{base.strip()} | {video['streamer']} #shorts"
    if len(titulo) > 100:
        titulo = base.strip()[: 100 - len(f" | {video['streamer']} #shorts") - 1] + f"… | {video['streamer']} #shorts"
    return titulo, video["legenda"] or ""


def publicar(arquivo, titulo, descricao, tags=(), prog=None):
    """Envia o vídeo e devolve o link do Short. prog(pct, etapa) mostra o progresso."""
    prog = prog or (lambda *a, **k: None)
    token = _token_de_acesso()
    metadados = {
        "snippet": {"title": titulo, "description": descricao[:4900], "tags": list(tags)[:15],
                    "categoryId": CATEGORIA_JOGOS, "defaultLanguage": "pt-BR"},
        "status": {"privacyStatus": PRIVACIDADE, "selfDeclaredMadeForKids": False},
    }
    tamanho = Path(arquivo).stat().st_size
    ini = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(tamanho)},
        data=json.dumps(metadados), timeout=30)
    if ini.status_code != 200 or "Location" not in ini.headers:
        raise RuntimeError(f"YouTube não aceitou o envio: {ini.text[:300]}")
    destino = ini.headers["Location"]

    # Envia em pedaços de 8 MB, retomando de onde parou se a conexão cair
    pedaco, enviado, falhas = 8 * 1024 * 1024, 0, 0
    with open(arquivo, "rb") as f:
        while enviado < tamanho:
            f.seek(enviado)
            dados = f.read(pedaco)
            fim = enviado + len(dados) - 1
            try:
                r = requests.put(destino, data=dados, timeout=300, headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Range": f"bytes {enviado}-{fim}/{tamanho}"})
            except requests.RequestException:
                falhas += 1
                if falhas > 5:
                    raise
                r = requests.put(destino, timeout=60, headers={
                    "Authorization": f"Bearer {token}", "Content-Range": f"bytes */{tamanho}"})
            if r.status_code in (200, 201):
                video_id = r.json()["id"]
                prog(100, "Publicado no YouTube", True)
                return f"https://youtube.com/shorts/{video_id}", r.json().get("status", {}).get("privacyStatus")
            if r.status_code == 308:  # recebido em parte
                faixa = r.headers.get("Range")
                enviado = int(faixa.split("-")[1]) + 1 if faixa else 0
                prog(enviado / tamanho * 99, f"Publicando no YouTube ({enviado * 100 // tamanho}%)")
                continue
            if r.status_code >= 500:
                falhas += 1
                if falhas > 5:
                    raise RuntimeError(f"YouTube instável: {r.status_code}")
                continue
            raise RuntimeError(f"YouTube recusou o vídeo: {r.text[:300]}")
    raise RuntimeError("Envio ao YouTube terminou sem confirmação.")
