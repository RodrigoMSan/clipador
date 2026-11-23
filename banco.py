"""Banco SQLite: clipes coletados e vídeos gerados."""
import json
import sqlite3
from datetime import datetime

from config import DB

ESQUEMA = """
CREATE TABLE IF NOT EXISTS clipes (
    id TEXT PRIMARY KEY,
    streamer TEXT,
    titulo TEXT,
    url TEXT,
    duracao REAL,
    views INTEGER,
    data TEXT,
    usado_em INTEGER
);
CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    streamer TEXT,
    clipes TEXT,
    arquivo TEXT,
    duracao REAL,
    legenda TEXT,
    status TEXT DEFAULT 'gerado',
    motivo TEXT,
    telegram_msg INTEGER,
    criado_em TEXT,
    decidido_em TEXT
);
CREATE TABLE IF NOT EXISTS meta (
    chave TEXT PRIMARY KEY,
    valor TEXT
);
"""


def conectar():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.executescript(ESQUEMA)
    colunas = {r[1] for r in con.execute("PRAGMA table_info(videos)")}
    if "url" not in colunas:  # link público do vídeo em 1080p (versão na nuvem)
        con.execute("ALTER TABLE videos ADD COLUMN url TEXT")
    if "youtube" not in colunas:  # link do Short publicado
        con.execute("ALTER TABLE videos ADD COLUMN youtube TEXT")
    return con


def meta(chave, padrao=None):
    with conectar() as con:
        r = con.execute("SELECT valor FROM meta WHERE chave=?", (chave,)).fetchone()
        return r[0] if r else padrao


def definir_meta(chave, valor):
    with conectar() as con:
        con.execute("INSERT INTO meta (chave, valor) VALUES (?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",
                    (chave, str(valor)))


def salvar_clipes(clipes):
    with conectar() as con:
        for c in clipes:
            con.execute(
                """INSERT INTO clipes (id, streamer, titulo, url, duracao, views, data)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET views=excluded.views, titulo=excluded.titulo""",
                (c["id"], c["streamer"], c["titulo"], c["url"], c["duracao"], c["views"], c["data"]),
            )


def clipes_livres(streamer):
    with conectar() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM clipes WHERE streamer=? AND usado_em IS NULL ORDER BY views DESC",
            (streamer,),
        )]


def criar_video(streamer, clipes, arquivo, duracao, legenda):
    with conectar() as con:
        cur = con.execute(
            "INSERT INTO videos (streamer, clipes, arquivo, duracao, legenda, criado_em) VALUES (?,?,?,?,?,?)",
            (streamer, json.dumps([c["id"] for c in clipes]), str(arquivo), duracao, legenda,
             datetime.now().isoformat(timespec="seconds")),
        )
        vid = cur.lastrowid
        con.executemany("UPDATE clipes SET usado_em=? WHERE id=?", [(vid, c["id"]) for c in clipes])
        return vid


def video(vid):
    with conectar() as con:
        r = con.execute("SELECT * FROM videos WHERE id=?", (vid,)).fetchone()
        return dict(r) if r else None


def atualizar_video(vid, **campos):
    if not campos:
        return
    sets = ", ".join(f"{k}=?" for k in campos)
    with conectar() as con:
        con.execute(f"UPDATE videos SET {sets} WHERE id=?", (*campos.values(), vid))


def liberar_clipes(vid):
    """Devolve os clipes de um vídeo reprovado para poderem ser usados de novo."""
    with conectar() as con:
        con.execute("UPDATE clipes SET usado_em=NULL WHERE usado_em=?", (vid,))


def videos_por_status(status):
    with conectar() as con:
        return [dict(r) for r in con.execute("SELECT * FROM videos WHERE status=? ORDER BY id", (status,))]


def clipes_do_video(vid):
    v = video(vid)
    ids = json.loads(v["clipes"]) if v else []
    with conectar() as con:
        por_id = {r["id"]: dict(r) for r in con.execute(
            f"SELECT * FROM clipes WHERE id IN ({','.join('?' * len(ids))})", ids)} if ids else {}
    return [por_id[i] for i in ids if i in por_id]
