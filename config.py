"""Configuração do Clipador. Ajuste aqui; segredos ficam no arquivo .env."""
from pathlib import Path
import os

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")

# Streamers autorizados (login da Twitch)
STREAMERS = ["alanzoka"]

# Períodos de clipes buscados na Twitch ("24hr", "7d", "30d", "all"), separados por vírgula.
# "all" dá o estoque dos melhores de sempre; "7d" e "24hr" trazem os clipes novos das lives.
PERIODOS = [p.strip() for p in os.getenv("CLIPADOR_PERIODOS", "all,7d,24hr").split(",") if p.strip()]
# Quantos clipes olhar por streamer a cada busca
CLIPES_POR_BUSCA = 100

# Duração do vídeo final (sem contar a tela final)
DURACAO_MIN = 65
DURACAO_MAX = 90
# Clipes muito curtos raramente seguram atenção
CLIPE_MIN = 8

# Nosso @ que aparece na tela final
NOSSO_ARROBA = os.getenv("CLIPADOR_ARROBA", "@clipador")
TELA_FINAL_SEG = 2.5

# Horários em que o bot monta e envia um vídeo sozinho (horário do computador), separados por vírgula.
# Deixe vazio para só gerar quando você mandar /gerar.
HORARIOS = [h.strip() for h in os.getenv("CLIPADOR_HORARIOS", "10:00,18:00").split(",") if h.strip()]

# Caminho relativo à pasta do projeto (evita o "C:" do Windows quebrar o filtro do FFmpeg)
FONTE = "assets/InterDisplay-Bold.otf"

# Pastas de trabalho
DADOS = Path(os.getenv("CLIPADOR_DADOS", BASE / "dados"))
BRUTOS = DADOS / "brutos"
PRONTOS = DADOS / "prontos"
APROVADOS = DADOS / "aprovados"
DB = DADOS / "clipador.db"
for p in (DADOS, BRUTOS, PRONTOS, APROVADOS):
    p.mkdir(parents=True, exist_ok=True)

# Na nuvem (GitHub Actions) o bot roda por um tempo limitado e salva o estado no próprio repositório
NA_NUVEM = os.getenv("GITHUB_ACTIONS") == "true"
MAX_MINUTOS = float(os.getenv("CLIPADOR_MAX_MINUTOS", "0"))  # 0 = sem limite

# Telegram (crie o bot no @BotFather e coloque o token no .env)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
