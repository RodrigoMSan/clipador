#!/usr/bin/env bash
# Roda o bot do Telegram uma vez, por poucos minutos, fora do GitHub Actions
# (tarefa agendada de hora em hora na nuvem do projeto). Faz o mesmo que o workflow:
# restaura o estado do ramo "estado", atende os botões, gera os vídeos às 18h, salva e desliga.
# Não posta em rede nenhuma: a postagem tem a tarefa própria (12h e 18h).
set -euo pipefail
cd "$(dirname "$0")"

if [ -z "${TELEGRAM_TOKEN:-}" ] || [ -z "${TELEGRAM_CHAT_ID:-}" ]; then
  echo "FALTA_TELEGRAM: adicione TELEGRAM_TOKEN e TELEGRAM_CHAT_ID nas variáveis do ambiente." >&2
  exit 2
fi
command -v ffmpeg >/dev/null || { apt-get update -qq && apt-get install -y -qq ffmpeg; }
pip install -q -r requirements.txt

export TZ=America/Sao_Paulo PYTHONIOENCODING=utf-8
export CLIPADOR_NUVEM=true
export CLIPADOR_ARROBA="${CLIPADOR_ARROBA:-@clipador}"
export CLIPADOR_HORARIOS="${CLIPADOR_HORARIOS:-18:00}"
export CLIPADOR_POR_HORARIO="${CLIPADOR_POR_HORARIO:-2}"
export CLIPADOR_MAX_MINUTOS="${CLIPADOR_MAX_MINUTOS:-3}"
export CLIPADOR_MAX_LOTE_MIN="${CLIPADOR_MAX_LOTE_MIN:-40}"
# Sem postar daqui (evita postar em dobro com a tarefa das 12h/18h)
export CLIPADOR_POSTAR=""
unset YOUTUBE_CLIENT_ID YOUTUBE_CLIENT_SECRET YOUTUBE_REFRESH_TOKEN META_TOKEN METRICOOL_TOKEN METRICOOL_USER_ID

exec python -u telegram_bot.py
