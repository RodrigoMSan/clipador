"""Publica Reels no Instagram e no Facebook da Playclips pela Graph API da Meta (grátis).

Variável: META_TOKEN (token do usuário de 60 dias, ou token da página, que não vence).
"""
import os
import time

import requests

G = "https://graph.facebook.com/v21.0"
TOKEN = os.getenv("META_TOKEN", "")


def configurado():
    return bool(TOKEN)


def _get(caminho, **params):
    r = requests.get(f"{G}/{caminho}", params={**params, "access_token": params.pop("token", TOKEN)}, timeout=60).json()
    if "error" in r:
        raise RuntimeError(f"Meta: {r['error'].get('message')}")
    return r


def _post(caminho, token, **dados):
    r = requests.post(f"{G}/{caminho}", data={**dados, "access_token": token}, timeout=120).json()
    if "error" in r:
        raise RuntimeError(f"Meta: {r['error'].get('error_user_msg') or r['error'].get('message')}")
    return r


def contas():
    """Página do Facebook (id, token) e conta do Instagram ligada a ela."""
    try:  # token de página: ele mesmo é a página
        eu = _get("me", fields="id,name,instagram_business_account")
        if "instagram_business_account" in eu:
            return eu["id"], TOKEN, eu["instagram_business_account"]["id"]
    except RuntimeError:
        pass
    paginas = _get("me/accounts", fields="id,name,access_token,instagram_business_account")["data"]
    p = next((x for x in paginas if x.get("instagram_business_account")), paginas[0])
    return p["id"], p["access_token"], (p.get("instagram_business_account") or {}).get("id")


def link_direto(url):
    """O link das Releases do GitHub redireciona; a Meta baixa melhor o endereço final."""
    with requests.get(url, stream=True, allow_redirects=True, timeout=60) as r:
        return r.url


def instagram_preparar(ig_id, token, url, legenda):
    c = _post(f"{ig_id}/media", token, media_type="REELS", video_url=url, caption=legenda[:2200], share_to_feed="true")
    for _ in range(60):  # até 10 min processando
        st = _get(c["id"], fields="status_code,status", token=token)
        if st.get("status_code") == "FINISHED":
            return c["id"]
        if st.get("status_code") == "ERROR":
            raise RuntimeError(f"Instagram recusou o vídeo: {st.get('status')}")
        time.sleep(10)
    raise RuntimeError("Instagram demorou demais para processar o vídeo.")


def instagram(url, legenda):
    _, token, ig_id = contas()
    if not ig_id:
        raise RuntimeError("A página não tem Instagram profissional ligado.")
    cont = instagram_preparar(ig_id, token, link_direto(url), legenda)
    media = _post(f"{ig_id}/media_publish", token, creation_id=cont)
    return _get(media["id"], fields="permalink", token=token).get("permalink")


def facebook(url, legenda):
    pagina, token, _ = contas()
    ini = _post(f"{pagina}/video_reels", token, upload_phase="start")
    r = requests.post(f"https://rupload.facebook.com/video-upload/v21.0/{ini['video_id']}",
                      headers={"Authorization": f"OAuth {token}", "file_url": link_direto(url)}, timeout=300).json()
    if not r.get("success"):
        raise RuntimeError(f"Facebook não aceitou o envio: {r}")
    _post(f"{pagina}/video_reels", token, upload_phase="finish", video_id=ini["video_id"],
          video_state="PUBLISHED", description=legenda[:2200])
    return f"https://www.facebook.com/reel/{ini['video_id']}"
