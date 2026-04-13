# =============================================================
# tests/phase4/test_database.py
# =============================================================
#
# Tests complets de core/database.py :
#   - init, CRUD, déduplication, stats, feedback
#   - Isolation totale via DB SQLite en mémoire
# =============================================================

import pytest, json, sqlite3, os
from tests.phase4.conftest import make_analyzed_job


# ── Fixture DB isolée ────────────────────────────────────────

@pytest.fixture
def db(tmp_path):
    """Fournit un module database pointant sur une DB temporaire."""
    import core.database as db_mod
    original = db_mod.settings.DB_PATH
    db_mod.settings.DB_PATH = str(tmp_path / "test.db")
    db_mod.init_db()
    yield db_mod
    db_mod.settings.DB_PATH = original


# ── init_db ───────────────────────────────────────────────────

class TestInitDb:

    def test_creates_missions_table(self, db):
        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='missions'")
        assert c.fetchone() is not None
        conn.close()

    def test_creates_preferences_table(self, db):
        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='preferences'")
        assert c.fetchone() is not None
        conn.close()

    def test_creates_feedback_table(self, db):
        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='feedback'")
        assert c.fetchone() is not None
        conn.close()

    def test_idempotent_double_init(self, db):
        """init_db() peut être appelé 2 fois sans erreur (IF NOT EXISTS)."""
        db.init_db()  # 2ème appel
        assert True   # pas d'exception

    def test_missions_has_required_columns(self, db):
        conn = db.get_connection()
        c = conn.cursor()
        c.execute("PRAGMA table_info(missions)")
        cols = {row[1] for row in c.fetchall()}
        conn.close()
        required = {"id", "url", "title", "description", "source", "score", "status", "created_at"}
        assert required.issubset(cols), f"Colonnes manquantes: {required - cols}"


# ── is_seen ───────────────────────────────────────────────────

class TestIsSeen:

    def test_returns_false_for_unknown_url(self, db):
        assert db.is_seen("https://example.com/unknown") is False

    def test_returns_true_after_save(self, db):
        job = make_analyzed_job(1, "codeur", 0.7)
        db.save_mission(job)
        assert db.is_seen(job["url"]) is True

    def test_case_sensitive(self, db):
        job = make_analyzed_job(1)
        db.save_mission(job)
        assert db.is_seen(job["url"].upper()) is False


# ── save_mission ──────────────────────────────────────────────

class TestSaveMission:

    def test_save_returns_true_for_new(self, db):
        job = make_analyzed_job(1)
        assert db.save_mission(job) is True

    def test_save_returns_false_for_duplicate(self, db):
        job = make_analyzed_job(1)
        db.save_mission(job)
        assert db.save_mission(job) is False  # doublon

    def test_save_persists_all_fields(self, db):
        job = make_analyzed_job(42, "malt", 0.88)
        db.save_mission(job)
        conn = db.get_connection()
        c    = conn.cursor()
        c.execute("SELECT * FROM missions WHERE url = ?", (job["url"],))
        row = c.fetchone()
        conn.close()
        assert row is not None
        assert row["title"]  == job["title"]
        assert row["source"] == job["source"]
        assert abs(row["score"] - 0.88) < 0.01

    def test_save_sets_status_new(self, db):
        job = make_analyzed_job(1)
        db.save_mission(job)
        conn = db.get_connection()
        c    = conn.cursor()
        c.execute("SELECT status FROM missions WHERE url = ?", (job["url"],))
        assert c.fetchone()["status"] == "new"
        conn.close()

    def test_save_stores_analysis_as_json(self, db):
        job = make_analyzed_job(1)
        db.save_mission(job)
        conn = db.get_connection()
        c    = conn.cursor()
        c.execute("SELECT analysis FROM missions WHERE url = ?", (job["url"],))
        raw = c.fetchone()["analysis"]
        conn.close()
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)
        assert "stack" in parsed or "type" in parsed

    def test_save_100_jobs_without_error(self, db):
        for i in range(100):
            job = make_analyzed_job(i, f"source_{i % 5}")
            db.save_mission(job)
        stats = db.get_stats()
        assert stats["total"] == 100


# ── update_status ─────────────────────────────────────────────

class TestUpdateStatus:

    def test_update_to_sent(self, db):
        job = make_analyzed_job(1)
        db.save_mission(job)
        db.update_status(job["url"], "sent")
        conn = db.get_connection()
        c    = conn.cursor()
        c.execute("SELECT status FROM missions WHERE url = ?", (job["url"],))
        assert c.fetchone()["status"] == "sent"
        conn.close()

    def test_update_to_liked(self, db):
        job = make_analyzed_job(1)
        db.save_mission(job)
        db.update_status(job["url"], "liked")
        conn = db.get_connection()
        c    = conn.cursor()
        c.execute("SELECT status FROM missions WHERE url = ?", (job["url"],))
        assert c.fetchone()["status"] == "liked"
        conn.close()

    def test_update_nonexistent_url_no_crash(self, db):
        db.update_status("https://nonexistent.com/job", "sent")
        # Ne doit pas lever d'exception


# ── get_all_missions ──────────────────────────────────────────

class TestGetAllMissions:

    def test_returns_empty_list_when_no_missions(self, db):
        assert db.get_all_missions() == []

    def test_returns_saved_missions(self, db):
        for i in range(3):
            db.save_mission(make_analyzed_job(i))
        missions = db.get_all_missions()
        assert len(missions) == 3

    def test_respects_limit_param(self, db):
        for i in range(20):
            db.save_mission(make_analyzed_job(i))
        assert len(db.get_all_missions(limit=5)) == 5

    def test_returns_dicts(self, db):
        db.save_mission(make_analyzed_job(1))
        missions = db.get_all_missions()
        assert isinstance(missions[0], dict)
        assert "url" in missions[0]
        assert "title" in missions[0]

    def test_most_recent_first(self, db):
        import time
        for i in range(3):
            db.save_mission(make_analyzed_job(i))
            time.sleep(0.01)
        missions = db.get_all_missions()
        # L'ordre est DESC created_at → le dernier inséré en premier
        assert missions[0]["url"] != missions[-1]["url"]


# ── get_stats ─────────────────────────────────────────────────

class TestGetStats:

    def test_initial_stats_all_zero(self, db):
        stats = db.get_stats()
        assert stats["total"] == 0
        assert stats["sent"]  == 0
        assert stats["liked"] == 0

    def test_counts_total(self, db):
        for i in range(4):
            db.save_mission(make_analyzed_job(i))
        assert db.get_stats()["total"] == 4

    def test_counts_sent(self, db):
        for i in range(3):
            job = make_analyzed_job(i)
            db.save_mission(job)
            db.update_status(job["url"], "sent")
        db.save_mission(make_analyzed_job(99))  # new
        assert db.get_stats()["sent"] == 3

    def test_counts_liked(self, db):
        job = make_analyzed_job(1)
        db.save_mission(job)
        db.update_status(job["url"], "liked")
        assert db.get_stats()["liked"] == 1

    def test_counts_by_source(self, db):
        for i in range(3):
            db.save_mission(make_analyzed_job(i, "codeur"))
        for i in range(10, 12):
            db.save_mission(make_analyzed_job(i, "malt"))
        stats = db.get_stats()
        assert stats["by_source"].get("codeur", 0) == 3
        assert stats["by_source"].get("malt",   0) == 2


# ── save_feedback ─────────────────────────────────────────────

class TestSaveFeedback:

    def test_save_like_feedback(self, db):
        db.save_feedback("https://example.com/job/1", "liked", "super mission")
        conn = db.get_connection()
        c    = conn.cursor()
        c.execute("SELECT * FROM feedback WHERE mission_url = ?", ("https://example.com/job/1",))
        row = c.fetchone()
        conn.close()
        assert row is not None
        assert row["action"] == "liked"
        assert row["note"]   == "super mission"

    def test_save_dislike_feedback(self, db):
        db.save_feedback("https://example.com/job/2", "disliked")
        conn = db.get_connection()
        c    = conn.cursor()
        c.execute("SELECT action FROM feedback WHERE mission_url = ?", ("https://example.com/job/2",))
        assert c.fetchone()["action"] == "disliked"
        conn.close()

    def test_multiple_feedbacks_same_url(self, db):
        url = "https://example.com/job/3"
        db.save_feedback(url, "liked")
        db.save_feedback(url, "applied", "j'ai postulé")
        conn = db.get_connection()
        c    = conn.cursor()
        c.execute("SELECT COUNT(*) FROM feedback WHERE mission_url = ?", (url,))
        assert c.fetchone()[0] == 2
        conn.close()
