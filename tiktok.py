"""Publicação no TikTok pela API oficial (Content Posting API, "Direct Post").

Variáveis (ambiente do projeto ou .env):
  TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET   do app em developers.tiktok.com
  TIKTOK_REFRESH_TOKEN                      gerado uma vez com --link / --codigo (vale 1 ano)
  TIKTOK_POSTAR=1                           liga a postagem pelo postar_youtube.py (só depois da auditoria)

Enquanto o app não passa pela auditoria do TikTok, a API só posta vídeos PRIVADOS (SELF_ONLY) e
exige que a conta esteja privada. Por isso TIKTOK_POSTAR fica desligado até a auditoria sair.

Uso:
  python tiktok.py --link                  mostra o link para autorizar a conta Playclips
  python tiktok.py --codigo "<endereço>"   troca o código pelo refresh token (cole o endereço inteiro)
  python tiktok.py --teste                 confere a autorização e mostra as opções da conta
  python tiktok.py --postar video.mp4 "legenda" [--privado]
"""
import math
import os
import secrets
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlencode, urlparse

import requests

CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY", "")
CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET", "")
REFRESH_TOKEN = os.getenv("TIKTOK_REFRESH_TOKEN", "")
POSTAR = os.getenv("TIKTOK_POSTAR", "") == "1"
REDIRECT_URI = os.getenv("TIKTOK_REDIRECT_URI", "https://rodrigomsan.github.io/clipador/tiktok.html")
ESCOPOS = "user.info.basic,video.publish"
API = "https://open.tiktokapis.com/v2"
CHUNK = 10 * 1024 * 1024  # entre 5 MB e 64 MB; o último pedaço absorve o resto


def configurado():
    return bool(CLIENT_KEY and CLIENT_SECRET and REFRESH_TOKEN)


def _erro(r):
    try:
        e = r.json().get("error") or {}
        return f"{r.status_code} {e.get('code')}: {e.get('message')}"
    except ValueError:
        return f"{r.status_code}: {r.text[:300]}"


def _token(dados):
    r = requests.post(f"{API}/oauth/token/", data={"client_key": CLIENT_KEY, "client_secret": CLIENT_SECRET, **dados},
                      headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    j = r.json()
    if "access_token" not in j:
        raise RuntimeError(f"TikTok recusou a autorização: {j.get('error_description') or j.get('error') or j}")
    return j


def _token_de_acesso():
    j = _token({"grant_type": "refresh_token", "refresh_token": REFRESH_TOKEN})
    if j.get("refresh_token") and j["refresh_token"] != REFRESH_TOKEN:
        # O TikTok pode trocar o refresh token. O antigo para de valer, então avise para atualizar a variável.
        print("AVISO_TIKTOK: o TIKTOK_REFRESH_TOKEN mudou. Atualize a variável com:", j["refresh_token"])
    return j["access_token"]


def _post(caminho, token, corpo=None):
    r = requests.post(f"{API}{caminho}", json=corpo or {}, timeout=60,
                      headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"})
    if r.status_code >= 300 or (r.json().get("error") or {}).get("code", "ok") != "ok":
        raise RuntimeError(f"TikTok {caminho}: {_erro(r)}")
    return r.json().get("data") or {}


def conta(token=None):
    """Dados da conta (nome, opções de privacidade, duração máxima)."""
    return _post("/post/publish/creator_info/query/", token or _token_de_acesso())


def publicar(arquivo, legenda, privado=False):
    """Envia o vídeo e espera o TikTok publicar. Devolve o link (ou o publish_id se o link não vier)."""
    token = _token_de_acesso()
    info = conta(token)
    opcoes = info.get("privacy_level_options") or []
    privacidade = "SELF_ONLY" if privado else "PUBLIC_TO_EVERYONE"
    if privacidade not in opcoes:
        raise RuntimeError(f"A conta não aceita {privacidade} agora (opções: {', '.join(opcoes) or 'nenhuma'}).")
    tamanho = Path(arquivo).stat().st_size
    if tamanho <= CHUNK:
        pedaco, total = tamanho, 1
    else:
        pedaco, total = CHUNK, tamanho // CHUNK
    dados = _post("/post/publish/video/init/", token, {
        "post_info": {"title": legenda[:2200], "privacy_level": privacidade, "disable_comment": False,
                      "disable_duet": False, "disable_stitch": False, "video_cover_timestamp_ms": 1000},
        "source_info": {"source": "FILE_UPLOAD", "video_size": tamanho, "chunk_size": pedaco,
                        "total_chunk_count": total},
    })
    publish_id, upload_url = dados["publish_id"], dados["upload_url"]
    with open(arquivo, "rb") as f:
        for i in range(total):
            inicio = i * pedaco
            fim = tamanho - 1 if i == total - 1 else inicio + pedaco - 1
            f.seek(inicio)
            corpo = f.read(fim - inicio + 1)
            for tentativa in range(3):
                r = requests.put(upload_url, data=corpo, timeout=300, headers={
                    "Content-Type": "video/mp4", "Content-Length": str(len(corpo)),
                    "Content-Range": f"bytes {inicio}-{fim}/{tamanho}"})
                if r.status_code in (201, 206):
                    break
                if r.status_code < 500 or tentativa == 2:
                    raise RuntimeError(f"Envio do vídeo ao TikTok falhou: {_erro(r)}")
                time.sleep(5)
    for _ in range(60):  # até ~10 min
        time.sleep(10)
        st = _post("/post/publish/status/fetch/", token, {"publish_id": publish_id})
        if st.get("status") == "PUBLISH_COMPLETE":
            ids = st.get("publicaly_available_post_id") or []
            usuario = info.get("creator_username")
            return f"https://www.tiktok.com/@{usuario}/video/{ids[0]}" if ids and usuario else f"publicado ({publish_id})"
        if st.get("status") == "FAILED":
            raise RuntimeError(f"TikTok não publicou: {st.get('fail_reason')}")
    return f"processando ({publish_id})"


def _link():
    estado = secrets.token_urlsafe(12)
    return "https://www.tiktok.com/v2/auth/authorize/?" + urlencode({
        "client_key": CLIENT_KEY, "scope": ESCOPOS, "response_type": "code",
        "redirect_uri": REDIRECT_URI, "state": estado})


def main():
    args = sys.argv[1:]
    if not (CLIENT_KEY and CLIENT_SECRET):
        sys.exit("Faltam TIKTOK_CLIENT_KEY e TIKTOK_CLIENT_SECRET no ambiente.")
    if "--link" in args:
        print("Abra, entre com a conta Playclips e autorize:\n" + _link())
    elif "--codigo" in args:
        valor = args[args.index("--codigo") + 1]
        codigo = parse_qs(urlparse(valor).query).get("code", [valor])[0] if "code=" in valor else valor
        j = _token({"grant_type": "authorization_code", "code": unquote(codigo), "redirect_uri": REDIRECT_URI})
        print("Escopos:", j.get("scope"))
        print("TIKTOK_REFRESH_TOKEN=" + j["refresh_token"])
    elif "--teste" in args:
        if not REFRESH_TOKEN:
            sys.exit("Falta TIKTOK_REFRESH_TOKEN.")
        info = conta()
        print("TikTok OK. Conta:", info.get("creator_nickname"), f"(@{info.get('creator_username')})")
        print("Privacidade possível:", ", ".join(info.get("privacy_level_options") or []))
        print("Duração máxima (s):", info.get("max_video_post_duration_sec"))
    elif "--postar" in args:
        i = args.index("--postar")
        print("TIKTOK:", publicar(args[i + 1], args[i + 2], privado="--privado" in args))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
