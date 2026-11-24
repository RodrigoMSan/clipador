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

# Horários em que o bot monta e envia vídeos sozinho (horário do computador), separados por vírgula.
# Deixe vazio para só gerar quando você mandar /gerar.
HORARIOS = [h.strip() for h in os.getenv("CLIPADOR_HORARIOS", "18:00").split(",") if h.strip()]
# Horários em que o bot publica sozinho o próximo vídeo aprovado no YouTube (um por horário).
# Vazio: publica logo depois do Aprovar (comportamento antigo).
POSTAR_HORARIOS = [h.strip() for h in os.getenv("CLIPADOR_POSTAR", "12:00,18:00").split(",") if h.strip()]
# Só começa a postar a partir desta data (AAAA-MM-DD); antes disso o Metricool cuida.
POSTAR_DESDE = os.getenv("CLIPADOR_POSTAR_DESDE", "")
# Quantos vídeos montar em cada horário (padrão: 2, os posts das 12h e 18h do dia seguinte)
POR_HORARIO = int(os.getenv("CLIPADOR_POR_HORARIO", "2") or 2)

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
# CLIPADOR_NUVEM=true faz o mesmo fora do GitHub (ex.: tarefa agendada na nuvem do projeto, rodar_nuvem.sh)
NO_GITHUB_ACTIONS = os.getenv("GITHUB_ACTIONS") == "true"
NA_NUVEM = NO_GITHUB_ACTIONS or os.getenv("CLIPADOR_NUVEM", "").lower() == "true"
MAX_MINUTOS = float(os.getenv("CLIPADOR_MAX_MINUTOS", "0"))  # 0 = sem limite

# Telegram (crie o bot no @BotFather e coloque o token no .env)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
