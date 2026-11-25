"""Deixa um vídeo editado com link público (para Instagram, Facebook e Metricool baixarem).

Sobe o arquivo num ramo `midia` do repositório, que é sempre substituído (fica só o último),
e devolve o link raw.githubusercontent.com. Funciona sem a API de Releases.
"""
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO = "https://github.com/RodrigoMSan/clipador"
RAW = "https://raw.githubusercontent.com/RodrigoMSan/clipador"


def publicar_arquivo(arquivo, nome=None, ramo="midia"):
    """Sobe o arquivo sozinho no ramo indicado (substituindo o que havia) e devolve o link público."""
    nome = nome or Path(arquivo).name
    with tempfile.TemporaryDirectory() as tmp:
        def git(*a):
            subprocess.run(["git", *a], cwd=tmp, check=True, capture_output=True)
        git("init", "-q", "-b", ramo)
        shutil.copy(arquivo, Path(tmp) / nome)
        git("add", nome)
        git("-c", "user.name=Clipador", "-c", "user.email=clipador@users.noreply.github.com",
            "commit", "-q", "-m", f"mídia {nome}")
        git("push", "-q", "-f", REPO, f"HEAD:{ramo}")
    return f"{RAW}/{ramo}/{nome}"
