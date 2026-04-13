# =============================================================
# tests/phase4/conftest.py — fixtures E2E Phase 4
# =============================================================
#
# Cette phase teste le système entier de bout en bout :
#   Collect → Analyze → Score → Notify → DB
# Sans aucun appel réseau réel — tout est simulé.
# =============================================================

import sys, os, json, sqlite3, asyncio, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

# ── Helpers partagés ─────────────────────────────────────────

def make_raw_job(n=1, source="codeur", score=None, with_tech=True) -> dict:
    """Crée un job brut simulant la sortie d'un scraper."""
    tech = "wordpress react nextjs" if with_tech else "cobol legacy"
    return {
        "title":       f"Développeur {tech.split()[0].capitalize()} freelance #{n}",
        "description": f"Mission {n}: {tech}. Remote. Budget 600-900€.",
        "url":         f"https://{source}.com/missions/{n}",
        "budget_raw":  f"{n * 300} €",
        "source":      source,
    }


def make_analyzed_job(n=1, source="codeur", score=0.75) -> dict:
    """Crée un job déjà analysé par l'IA (simulé)."""
    job = make_raw_job(n, source)
    job["analysis"] = {
        "type":          "web",
        "stack":         ["wordpress", "react"],
        "budget_estime": n * 300,
        "niveau":        "intermédiaire",
        "remote":        True,
        "resume":        f"Mission dev web #{n}",
        "est_freelance": True,
        "langue":        "fr",
    }
    job["score"] = score
    job["score_detail"] = {
        "keywords": {"hits": ["wordpress", "react"], "score": 0.24},
        "budget":   {"value": n * 300, "score": 0.15},
        "remote":   True,
    }
    return job


def make_batch(n=5, sources=None, min_score=0.3) -> list:
    """Crée un batch de jobs analysés de sources variées."""
    if sources is None:
        sources = ["codeur", "malt", "upwork", "hackernews", "linkedin"]
    jobs = []
    for i in range(n):
        src   = sources[i % len(sources)]
        score = min_score + (i * 0.12)
        jobs.append(make_analyzed_job(i + 1, src, min(score, 1.0)))
    return jobs


@pytest.fixture
def tmp_db(tmp_path):
    """Base SQLite temporaire isolée pour chaque test."""
    db_path = str(tmp_path / "test_missions.db")
    # Patch settings.DB_PATH
    with patch("config.settings.settings") as mock_settings:
        mock_settings.DB_PATH              = db_path
        mock_settings.TELEGRAM_TOKEN      = "fake_token"
        mock_settings.TELEGRAM_CHAT_ID    = "12345"
        mock_settings.OPENAI_API_KEY      = ""
        mock_settings.OPENAI_MODEL        = "gpt-4o-mini"
        mock_settings.REQUEST_DELAY       = 0.0
        mock_settings.LOOP_INTERVAL       = 300
        mock_settings.MIN_SCORE           = 0.4
        mock_settings.PREFERRED_KEYWORDS  = ["wordpress", "react", "nextjs", "seo"]
        mock_settings.NEGATIVE_KEYWORDS   = ["cobol", "stagiaire"]
        mock_settings.MIN_BUDGET          = 200
        mock_settings.PREFERRED_LANGS     = ["fr"]
        mock_settings.SOURCES_ENABLED     = ["codeur", "malt"]
        mock_settings.TWITTER_BEARER_TOKEN = ""
        yield db_path


@pytest.fixture
def real_db(tmp_path):
    """Base SQLite réelle initialisée proprement."""
    db_path = str(tmp_path / "missions.db")
    # On réimporte avec le bon path
    import core.database as db_mod
    original = db_mod.settings.DB_PATH
    db_mod.settings.DB_PATH = db_path
    db_mod.init_db()
    yield db_mod, db_path
    db_mod.settings.DB_PATH = original


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)
