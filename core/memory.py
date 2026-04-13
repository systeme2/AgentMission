# =============================================================
# core/memory.py — apprentissage des préférences utilisateur
# =============================================================

import json
from core.database import get_connection, save_feedback
from config.settings import settings


def get_preferences() -> dict:
    """Récupère les préférences apprises depuis la DB."""
    conn = get_connection()
    c = conn.cursor()
    # Auto-create table si absente (évite l'erreur en environnement de test propre)
    c.execute("""CREATE TABLE IF NOT EXISTS preferences (
        id    INTEGER PRIMARY KEY AUTOINCREMENT,
        key   TEXT UNIQUE,
        value TEXT
    )""")
    conn.commit()
    c.execute("SELECT key, value FROM preferences")
    rows = c.fetchall()
    conn.close()

    prefs = {
        "liked_keywords": list(settings.PREFERRED_KEYWORDS),
        "disliked_keywords": list(settings.NEGATIVE_KEYWORDS),
        "liked_sources": [],
        "min_score_override": None,
    }

    for key, value in rows:
        try:
            prefs[key] = json.loads(value)
        except Exception:
            prefs[key] = value

    return prefs


def set_preference(key: str, value):
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO preferences (key, value) VALUES (?, ?)",
        (key, json.dumps(value))
    )
    conn.commit()
    conn.close()


def record_like(job: dict):
    """Quand tu likes une mission → extrait les mots clés et les mémorise."""
    prefs = get_preferences()
    words = _extract_keywords(job.get("title", "") + " " + job.get("description", ""))

    liked = prefs.get("liked_keywords", [])
    for w in words:
        if w not in liked:
            liked.append(w)

    set_preference("liked_keywords", liked[:100])  # max 100
    save_feedback(job["url"], "liked")
    print(f"💚 Like enregistré pour : {job['title'][:60]}")


def record_dislike(job: dict):
    """Quand tu dislikes une mission → évite ce genre à l'avenir."""
    prefs = get_preferences()
    words = _extract_keywords(job.get("title", "") + " " + job.get("description", ""))

    disliked = prefs.get("disliked_keywords", [])
    for w in words:
        if w not in disliked:
            disliked.append(w)

    set_preference("disliked_keywords", disliked[:100])
    save_feedback(job["url"], "disliked")
    print(f"🔴 Dislike enregistré pour : {job['title'][:60]}")


def apply_memory_to_score(job: dict, base_score: float) -> float:
    """Ajuste le score en fonction des préférences mémorisées."""
    prefs = get_preferences()
    text = (job.get("title", "") + " " + job.get("description", "")).lower()

    boost = 0.0
    penalty = 0.0

    for kw in prefs.get("liked_keywords", []):
        if kw.lower() in text:
            boost += 0.05

    for kw in prefs.get("disliked_keywords", []):
        if kw.lower() in text:
            penalty += 0.1

    final = min(1.0, max(0.0, base_score + boost - penalty))
    return round(final, 3)


def _extract_keywords(text: str) -> list:
    """Extrait des mots-clés simples (2+ lettres, pas stopwords)."""
    stopwords = {"le","la","les","de","du","un","une","des","et","en","à","au","avec","pour","sur","qui","que","dans"}
    words = text.lower().split()
    return [w.strip(".,!?()[]") for w in words if len(w) > 3 and w not in stopwords]
