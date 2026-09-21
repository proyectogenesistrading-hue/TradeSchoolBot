"""
Capa de datos en SQLite (100% gratis, un solo archivo, sin servidor externo).
Guarda usuarios, estadísticas de quiz y temas consultados.
"""
import sqlite3
from contextlib import contextmanager

DB_PATH = "quizbot.db"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
                idioma_video TEXT DEFAULT 'es'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS quiz_stats (
                user_id INTEGER PRIMARY KEY,
                correctas INTEGER DEFAULT 0,
                incorrectas INTEGER DEFAULT 0,
                racha_actual INTEGER DEFAULT 0,
                mejor_racha INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS consultas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                topic_id TEXT,
                fecha TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)


def ensure_user(user_id: int, username: str | None):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
            (user_id, username),
        )
        conn.execute(
            "INSERT OR IGNORE INTO quiz_stats (user_id) VALUES (?)",
            (user_id,),
        )


def log_consulta(user_id: int, topic_id: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO consultas (user_id, topic_id) VALUES (?, ?)",
            (user_id, topic_id),
        )


def registrar_respuesta(user_id: int, correcta: bool):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT correctas, incorrectas, racha_actual, mejor_racha FROM quiz_stats WHERE user_id=?",
            (user_id,),
        ).fetchone()
        correctas, incorrectas, racha, mejor = row
        if correcta:
            correctas += 1
            racha += 1
            mejor = max(mejor, racha)
        else:
            incorrectas += 1
            racha = 0
        conn.execute(
            """UPDATE quiz_stats
               SET correctas=?, incorrectas=?, racha_actual=?, mejor_racha=?
               WHERE user_id=?""",
            (correctas, incorrectas, racha, mejor, user_id),
        )


def get_stats(user_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT correctas, incorrectas, racha_actual, mejor_racha FROM quiz_stats WHERE user_id=?",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None


def set_idioma_video(user_id: int, idioma: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET idioma_video=? WHERE user_id=?", (idioma, user_id)
        )


def get_idioma_video(user_id: int) -> str:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT idioma_video FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        return row["idioma_video"] if row else "es"