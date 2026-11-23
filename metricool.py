"""Publicação pelo Metricool (plano Advanced): um único agendamento vai para YouTube Shorts,
TikTok, Instagram Reels e Facebook Reels.

Variáveis (Secrets do GitHub ou .env):
  METRICOOL_TOKEN     Configurações da conta > API (token de acesso)
  METRICOOL_USER_ID   o número depois de "userId=" no endereço do Metricool
  METRICOOL_BLOG_ID   o número depois de "blogId=" (a marca)
  METRICOOL_REDES     redes separadas por vírgula (padrão: youtube,tiktok,instagram,facebook)
  METRICOOL_ATRASO_MIN  minutos entre aprovar e publicar (padrão: 5)
"""
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

TOKEN = os.getenv("METRICOOL_TOKEN", "")
USER_ID = os.getenv("METRICOOL_USER_ID", "")
BLOG_ID = os.getenv("METRICOOL_BLOG_ID", "")
REDES = [r.strip() for r in os.getenv("METRICOOL_REDES", "youtube,tiktok,instagram,facebook").split(",") if r.strip()]
ATRASO_MIN = int(os.getenv("METRICOOL_ATRASO_MIN", "5"))
FUSO = "America/Sao_Paulo"
API = "https://app.metricool.com/api"


def configurado():
    return bool(TOKEN and USER_ID and BLOG_ID)


def _corpo(url_video, titulo, texto, quando):
    dados = {
        "publicationDate": {"dateTime": quando.strftime("%Y-%m-%dT%H:%M:%S"), "timezone": FUSO},
        "text": texto,
        "providers": [{"network": r} for r in REDES],
        "media": [url_video],
        "saveExternalMediaFiles": True,
        "autoPublish": True,
        "draft": False,
    }
    if "youtube" in REDES:
        dados["youtubeData"] = {"title": titulo[:100], "type": "short", "privacy": "public",
                                "madeForKids": False, "category": "GAMING"}
    if "tiktok" in REDES:
        dados["tiktokData"] = {"privacyOption": "PUBLIC_TO_EVERYONE"}
    if "instagram" in REDES:
        dados["instagramData"] = {"type": "REEL", "showReelOnFeed": True}
    if "facebook" in REDES:
        dados["facebookData"] = {"type": "REEL", "title": titulo[:255]}
    return dados


def agendar(url_video, titulo, texto):
    """Agenda o vídeo (link público) nas redes. Devolve (id do post, horário)."""
    if not url_video:
        raise RuntimeError("O vídeo não tem link público (ele só existe quando o bot roda no GitHub).")
    quando = datetime.now(ZoneInfo(FUSO)) + timedelta(minutes=ATRASO_MIN)
    r = requests.post(f"{API}/v2/scheduler/posts", params={"blogId": BLOG_ID, "userId": USER_ID},
                      headers={"X-Mc-Auth": TOKEN, "Content-Type": "application/json"},
                      json=_corpo(url_video, titulo, texto, quando), timeout=120)
    if r.status_code >= 300:
        raise RuntimeError(f"Metricool recusou ({r.status_code}): {r.text[:300]}")
    try:
        dados = r.json()
    except ValueError:
        dados = {}
    post = dados.get("data", dados) if isinstance(dados, dict) else {}
    return (post.get("id") if isinstance(post, dict) else None), quando.strftime("%H:%M")
