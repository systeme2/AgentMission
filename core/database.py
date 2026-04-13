# =============================================================
# core/database.py — SQLite persistance + déduplication
# =============================================================

import sqlite3
import json
import os
from datetime import datetime
from config.settings import settings


def get_connection():
    os.makedirs(os.path.dirname(settings.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS missions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            url         TEXT UNIQUE NOT NULL,
            title       TEXT,
            description TEXT,
            source      TEXT,
            score       REAL,
            analysis    TEXT,       -- JSON analysé par IA
            status      TEXT DEFAULT 'new',   -- new | sent | archived | liked | disliked
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS preferences (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            key     TEXT UNIQUE,
            value   TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            mission_url TEXT,
            action      TEXT,   -- liked | disliked | applied
            note        TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
    conn.close()
    print("✅ Base de données initialisée")


def is_seen(url: str) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT 1 FROM missions WHERE url = ?", (url,))
    result = c.fetchone()
    conn.close()
    return result is not None


def save_mission(job: dict) -> bool:
    """Sauvegarde une mission. Retourne False si déjà existante."""
    if is_seen(job["url"]):
        return False
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO missions (url, title, description, source, score, analysis, status)
            VALUES (?, ?, ?, ?, ?, ?, 'new')
        """, (
            job.get("url"),
            job.get("title"),
            job.get("description", ""),
            job.get("source", "unknown"),
            job.get("score", 0.0),
            json.dumps(job.get("analysis", {}), ensure_ascii=False)
        ))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def update_status(url: str, status: str):
    conn = get_connection()
    conn.execute("UPDATE missions SET status = ? WHERE url = ?", (status, url))
    conn.commit()
    conn.close()


def get_all_missions(limit=50):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM missions ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_stats():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as total FROM missions")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) as sent FROM missions WHERE status = 'sent'")
    sent = c.fetchone()[0]
    c.execute("SELECT COUNT(*) as liked FROM missions WHERE status = 'liked'")
    liked = c.fetchone()[0]
    c.execute("SELECT source, COUNT(*) as n FROM missions GROUP BY source")
    by_source = {r[0]: r[1] for r in c.fetchall()}
    conn.close()
    return {"total": total, "sent": sent, "liked": liked, "by_source": by_source}


def save_feedback(url: str, action: str, note: str = ""):
    conn = get_connection()
    conn.execute(
        "INSERT INTO feedback (mission_url, action, note) VALUES (?, ?, ?)",
        (url, action, note)
    )
    conn.commit()
    conn.close()
