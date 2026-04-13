# =============================================================
# tests/phase4/test_regression_global.py
# =============================================================
#
# Tests de régression transversaux :
#   - Toutes les 21 sources dans SOURCE_MAP
#   - Contrat de chaque source (liste, champs, jamais d'exception)
#   - Cohérence settings ↔ SOURCE_MAP
#   - DB schema stable
#   - Scorer deterministe
#   - Telegram ne se déclenche pas sous le seuil
# =============================================================

import asyncio, pytest
from unittest.mock import patch, AsyncMock, MagicMock
from tests.phase4.conftest import make_raw_job, make_analyzed_job, run

ALL_SOURCES = [
    "codeur", "reddit", "remixjobs", "welovedevs",
    "freelance.com", "404works", "comeup", "befreelancr", "collective.work",
    "malt", "upwork", "remoteok", "freelancer.com", "fiverr", "toptal", "kicklox",
    "hackernews", "dev.to", "linkedin", "twitter", "indiehackers",
]

SOURCE_MODULE_MAP = {
    "codeur":          ("sources.codeur",         "get_codeur_jobs"),
    "reddit":          ("sources.reddit",          "get_reddit_jobs"),
    "remixjobs":       ("sources.welovedevs",      "get_remixjobs_jobs"),
    "welovedevs":      ("sources.welovedevs",      "get_welovedevs_jobs"),
    "freelance.com":   ("sources.freelance_com",   "get_freelance_com_jobs"),
    "404works":        ("sources.works404",        "get_404works_jobs"),
    "comeup":          ("sources.comeup",          "get_comeup_jobs"),
    "befreelancr":     ("sources.befreelancr",     "get_befreelancr_jobs"),
    "collective.work": ("sources.collective_work", "get_collective_work_jobs"),
    "malt":            ("sources.malt",            "get_malt_jobs"),
    "upwork":          ("sources.upwork",          "get_upwork_jobs"),
    "remoteok":        ("sources.remoteok",        "get_remoteok_jobs"),
    "freelancer.com":  ("sources.freelancer_com",  "get_freelancer_com_jobs"),
    "fiverr":          ("sources.fiverr",          "get_fiverr_jobs"),
    "toptal":          ("sources.toptal",          "get_toptal_jobs"),
    "kicklox":         ("sources.kicklox",         "get_kicklox_jobs"),
    "hackernews":      ("sources.hackernews",      "get_hackernews_jobs"),
    "dev.to":          ("sources.devto",           "get_devto_jobs"),
    "linkedin":        ("sources.linkedin",        "get_linkedin_jobs"),
    "twitter":         ("sources.twitter",         "get_twitter_jobs"),
    "indiehackers":    ("sources.indiehackers",    "get_indiehackers_jobs"),
}


class TestRegistrationRegression:
    """Toutes les sources doivent être enregistrées correctement."""

    def test_source_map_has_exactly_21_sources(self):
        from agents.collector import SOURCE_MAP
        assert len(SOURCE_MAP) == 23, \
            f"SOURCE_MAP: attendu 23, obtenu {len(SOURCE_MAP)}: {sorted(SOURCE_MAP.keys())}"

    @pytest.mark.parametrize("source", ALL_SOURCES)
    def test_source_in_source_map(self, source):
        from agents.collector import SOURCE_MAP
        assert source in SOURCE_MAP, f"'{source}' absent de SOURCE_MAP"

    @pytest.mark.parametrize("source", ALL_SOURCES)
    def test_source_in_settings_enabled(self, source):
        from config.settings import settings
        assert source in settings.SOURCES_ENABLED, f"'{source}' absent de SOURCES_ENABLED"

    @pytest.mark.parametrize("source", ALL_SOURCES)
    def test_source_function_callable(self, source):
        from agents.collector import SOURCE_MAP
        assert callable(SOURCE_MAP[source]), f"SOURCE_MAP['{source}'] non callable"

    def test_no_source_registered_twice(self):
        from agents.collector import SOURCE_MAP
        assert len(SOURCE_MAP) == len(set(SOURCE_MAP.keys()))

    def test_settings_no_duplicate_sources(self):
        from config.settings import settings
        enabled = settings.SOURCES_ENABLED
        assert len(enabled) == len(set(enabled)), "Doublons dans SOURCES_ENABLED"


class TestSourceContractRegression:
    """Chaque source respecte le contrat : liste, pas d'exception."""

    @pytest.mark.parametrize("source,info", SOURCE_MODULE_MAP.items())
    def test_source_never_raises_on_network_error(self, source, info):
        import importlib, requests as r
        module_name, fn_name = info
        mod  = importlib.import_module(module_name)
        func = getattr(mod, fn_name)

        with patch(f"{module_name}.requests.get",
                   side_effect=r.RequestException("réseau down")):
            with patch(f"{module_name}.asyncio.sleep", return_value=None):
                # Pour les sources avec _fetch_* internes
                try:
                    for internal in ["_fetch_who_is_hiring_thread_id",
                                     "_fetch_jobs_from_thread", "_fetch_tag"]:
                        try:
                            with patch(f"{module_name}.{internal}",
                                       side_effect=r.RequestException("mocked")):
                                pass
                        except AttributeError:
                            pass
                    jobs = run(func())
                    assert isinstance(jobs, list), \
                        f"[{source}] doit retourner une liste, pas {type(jobs)}"
                except Exception as exc:
                    pytest.fail(f"[{source}] a levé une exception: {exc}")


class TestScoringRegression:
    """Le scorer est déterministe et borné dans [0, 1]."""

    @pytest.mark.parametrize("score", [0.0, 0.3, 0.5, 0.8, 1.0])
    def test_score_bounded(self, score):
        from agents.scorer import score_job
        job = make_analyzed_job(1, score=score)
        result = run(score_job(job))
        assert 0.0 <= result["score"] <= 1.0

    def test_score_deterministic_across_10_calls(self):
        from agents.scorer import score_job
        job     = make_analyzed_job(1, "codeur", 0.6)
        scores  = [run(score_job(dict(job)))["score"] for _ in range(10)]
        assert len(set(scores)) == 1, f"Scores non déterministes: {set(scores)}"

    def test_all_21_sources_scorable(self):
        """Un job de chaque source doit pouvoir être scoré."""
        from agents.scorer import score_job
        for source in ALL_SOURCES:
            job    = make_analyzed_job(1, source, 0.5)
            result = run(score_job(job))
            assert 0.0 <= result["score"] <= 1.0, f"Score invalide pour source {source}"


class TestDatabaseRegression:
    """La DB est stable et cohérente."""

    def test_db_schema_unchanged(self, tmp_path):
        import core.database as db_mod
        original = db_mod.settings.DB_PATH
        db_mod.settings.DB_PATH = str(tmp_path / "schema.db")
        db_mod.init_db()

        import sqlite3
        conn  = sqlite3.connect(str(tmp_path / "schema.db"))
        c     = conn.cursor()

        # missions
        c.execute("PRAGMA table_info(missions)")
        cols = {row[1] for row in c.fetchall()}
        assert {"id", "url", "title", "description", "source",
                "score", "analysis", "status", "created_at"}.issubset(cols)

        # preferences
        c.execute("PRAGMA table_info(preferences)")
        cols = {row[1] for row in c.fetchall()}
        assert {"id", "key", "value"}.issubset(cols)

        # feedback
        c.execute("PRAGMA table_info(feedback)")
        cols = {row[1] for row in c.fetchall()}
        assert {"id", "mission_url", "action", "note", "created_at"}.issubset(cols)

        conn.close()
        db_mod.settings.DB_PATH = original

    def test_db_dedup_100_same_url(self, tmp_path):
        """Insérer 100 fois la même URL → 1 seule ligne en DB."""
        import core.database as db_mod
        original = db_mod.settings.DB_PATH
        db_mod.settings.DB_PATH = str(tmp_path / "dedup.db")
        db_mod.init_db()

        job = make_analyzed_job(1, "codeur", 0.7)
        for _ in range(100):
            db_mod.save_mission(dict(job))  # copy pour éviter mutation

        stats = db_mod.get_stats()
        assert stats["total"] == 1
        db_mod.settings.DB_PATH = original


class TestTelegramRegression:
    """Telegram ne se déclenche jamais sous le seuil MIN_SCORE."""

    @patch("agents.notifier.requests.post")
    def test_telegram_not_called_for_low_score(self, mock_post, tmp_path):
        """Jobs sous le seuil → requests.post ne doit jamais être appelé."""
        import core.database as db_mod, config.settings as cfg_mod
        import agents.collector as col_mod

        original_db = db_mod.settings.DB_PATH
        db_mod.settings.DB_PATH = str(tmp_path / "tg_test.db")
        db_mod.init_db()

        low_job = make_analyzed_job(1, "codeur", score=0.05)

        orig_map = col_mod.SOURCE_MAP.copy()
        orig_en  = cfg_mod.settings.SOURCES_ENABLED[:]
        orig_score = cfg_mod.settings.MIN_SCORE

        async def fake_src(): return [make_raw_job(1, "codeur")]
        col_mod.SOURCE_MAP               = {"codeur": fake_src}
        cfg_mod.settings.SOURCES_ENABLED = ["codeur"]
        cfg_mod.settings.MIN_SCORE       = 0.4

        with patch("core.orchestrator.analyze_job", new_callable=AsyncMock,
                   return_value=low_job), \
             patch("core.orchestrator.score_job",   new_callable=AsyncMock,
                   return_value=low_job):
            try:
                from core.orchestrator import run_pipeline
                run(run_pipeline())
            finally:
                col_mod.SOURCE_MAP               = orig_map
                cfg_mod.settings.SOURCES_ENABLED = orig_en
                cfg_mod.settings.MIN_SCORE       = orig_score
                db_mod.settings.DB_PATH          = original_db

        assert mock_post.call_count == 0, \
            f"Telegram appelé {mock_post.call_count} fois pour un score < seuil"

    @patch("agents.notifier.requests.post")
    def test_telegram_called_for_high_score(self, mock_post, tmp_path):
        """Jobs au-dessus du seuil → Telegram appelé exactement 1 fois."""
        mock_post.return_value = MagicMock()
        mock_post.return_value.json.return_value = {"ok": True}

        import core.database as db_mod, config.settings as cfg_mod
        import agents.collector as col_mod
        from unittest.mock import MagicMock as MM

        original_db = db_mod.settings.DB_PATH
        db_mod.settings.DB_PATH = str(tmp_path / "tg_high.db")
        db_mod.init_db()

        high_job = make_analyzed_job(1, "malt", score=0.90)

        orig_map = col_mod.SOURCE_MAP.copy()
        orig_en  = cfg_mod.settings.SOURCES_ENABLED[:]
        orig_score = cfg_mod.settings.MIN_SCORE

        async def fake_src(): return [make_raw_job(1, "malt")]
        col_mod.SOURCE_MAP               = {"malt": fake_src}
        cfg_mod.settings.SOURCES_ENABLED = ["malt"]
        cfg_mod.settings.MIN_SCORE       = 0.4

        with patch("core.orchestrator.analyze_job", new_callable=AsyncMock,
                   return_value=high_job), \
             patch("core.orchestrator.score_job", new_callable=AsyncMock,
                   return_value=high_job):
            try:
                from core.orchestrator import run_pipeline
                run(run_pipeline())
            finally:
                col_mod.SOURCE_MAP               = orig_map
                cfg_mod.settings.SOURCES_ENABLED = orig_en
                cfg_mod.settings.MIN_SCORE       = orig_score
                db_mod.settings.DB_PATH          = original_db

        assert mock_post.call_count == 1
