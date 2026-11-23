"""Funções para rodar no GitHub Actions, onde o computador é apagado a cada execução.

- O banco (clipes usados, vídeos e decisões) fica salvo no ramo "estado" do repositório.
- Os vídeos em 1080p ficam guardados nas Releases do repositório, com um link público
  (que depois serve para o Metricool publicar).
"""
import os
import shutil
import sqlite3
import subprocess
import threading
from datetime import datetime
from pathlib import Path

from config import DB, NA_NUVEM

RAMO = "estado"
PASTA_ESTADO = Path(os.getenv("RUNNER_TEMP", "/tmp")) / "clipador-estado"
_trava = threading.Lock()


def _rodar(*cmd, cwd=None, checar=True):
    r = subprocess.run(list(cmd), cwd=cwd, capture_output=True, text=True)
    if checar and r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:3])}: {r.stderr.strip()[-500:]}")
    return r


def restaurar_estado():
    """Traz o banco salvo na última execução (se existir)."""
    if not NA_NUVEM:
        return
    _rodar("git", "config", "--global", "user.name", "clipador-bot")
    _rodar("git", "config", "--global", "user.email", "clipador-bot@users.noreply.github.com")
    tem_ramo = _rodar("git", "fetch", "origin", RAMO, checar=False).returncode == 0
    if PASTA_ESTADO.exists():
        shutil.rmtree(PASTA_ESTADO)
    if tem_ramo:
        _rodar("git", "worktree", "add", "-B", RAMO, str(PASTA_ESTADO), f"origin/{RAMO}")
        salvo = PASTA_ESTADO / "clipador.db"
        if salvo.exists():
            shutil.copy(salvo, DB)
            print("Estado restaurado da última execução.")
    else:
        _rodar("git", "worktree", "add", "--orphan", "-b", RAMO, str(PASTA_ESTADO))
        print("Primeira execução: começando com o banco vazio.")


def salvar_estado(motivo="atualização"):
    """Copia o banco para o ramo "estado" e envia para o GitHub."""
    if not NA_NUVEM or not DB.exists():
        return
    with _trava:
        destino = PASTA_ESTADO / "clipador.db"
        with sqlite3.connect(DB) as src, sqlite3.connect(destino) as dst:
            src.backup(dst)  # cópia consistente mesmo com o bot rodando
        _rodar("git", "add", "clipador.db", cwd=PASTA_ESTADO)
        if _rodar("git", "diff", "--cached", "--quiet", cwd=PASTA_ESTADO, checar=False).returncode == 0:
            return  # nada mudou
        _rodar("git", "commit", "-m", f"estado: {motivo}", cwd=PASTA_ESTADO)
        for _ in range(3):
            if _rodar("git", "push", "origin", f"HEAD:{RAMO}", cwd=PASTA_ESTADO, checar=False).returncode == 0:
                return
        print("Aviso: não consegui salvar o estado no GitHub.")


def guardar_video(arquivo):
    """Sobe o vídeo para a Release do mês e devolve o link público de download."""
    if not NA_NUVEM:
        return None
    repo = os.environ["GITHUB_REPOSITORY"]
    tag = "videos-" + datetime.now().strftime("%Y-%m")
    if _rodar("gh", "release", "view", tag, checar=False).returncode != 0:
        _rodar("gh", "release", "create", tag, "--title", f"Vídeos {datetime.now():%m/%Y}",
               "--notes", "Vídeos montados pelo Clipador (1080x1920).", "--latest=false")
    _rodar("gh", "release", "upload", tag, str(arquivo), "--clobber")
    return f"https://github.com/{repo}/releases/download/{tag}/{Path(arquivo).name}"
