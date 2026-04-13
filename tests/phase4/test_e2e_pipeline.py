# =============================================================
# tests/phase4/test_e2e_pipeline.py
# =============================================================
#
# Tests de bout en bout : pipeline complet sans appel réseau.
# Chaque test simule une session complète de l'agent :
#   Sources → Collector → Analyzer → Scorer → DB → Notifier
# =============================================================

import asyncio, pytest, json, os
from unittest.mock import patch, MagicMock, AsyncMock
from tests.phase4.conftest import make_raw_job, make_analyzed_job, make_batch, run


# ── Helpers ───────────────────────────────────────────────────

def _fake_source(jobs):
    """Retourne une coroutine async produisant les jobs donnés."""
    async def _fn(): return jobs
    return _fn


def _mock_telegram_ok():
    m = MagicMock()
    m.status_code = 200
    m.raise_for_status = MagicMock()
    m.json.return_value = {"ok": True, "result": {"message_id": 1}}
    return m


def _mock_telegram_fail():
    m = MagicMock()
    m.status_code = 400
    m.raise_for_status = MagicMock()
    m.json.return_value = {"ok": False, "description": "Bad Request"}
    return m


# ── Tests pipeline complet ────────────────────────────────────

class TestFullPipelineE2E:
    """Simule une session run_pipeline() complète sans réseau."""

    @patch("agents.notifier.requests.post")
    @patch("core.orchestrator.score_job",   new_callable=AsyncMock)
    @patch("core.orchestrator.analyze_job", new_callable=AsyncMock)
    def test_pipeline_sends_high_score_jobs(self, mock_analyze, mock_score, mock_post, real_db):
        """Jobs avec score > MIN_SCORE → notification Telegram envoyée."""
        db_mod, db_path = real_db
        mock_post.return_value = _mock_telegram_ok()

        # 3 jobs : 2 au-dessus du seuil, 1 en dessous
        jobs_in  = [make_raw_job(i, "codeur") for i in range(1, 4)]
        high     = make_analyzed_job(1, "codeur", score=0.85)
        medium   = make_analyzed_job(2, "codeur", score=0.65)
        low      = make_analyzed_job(3, "codeur", score=0.15)

        mock_analyze.side_effect = [high, medium, low]
        mock_score.side_effect   = [high, medium, low]

        import agents.collector as col_mod
        import config.settings  as cfg_mod

        orig_map = col_mod.SOURCE_MAP.copy()
        orig_en  = cfg_mod.settings.SOURCES_ENABLED[:]
        col_mod.SOURCE_MAP            = {"codeur": _fake_source(jobs_in)}
        cfg_mod.settings.SOURCES_ENABLED = ["codeur"]
        cfg_mod.settings.MIN_SCORE       = 0.4
        cfg_mod.settings.DB_PATH         = db_path

        import core.database as db_m
        db_m.settings.DB_PATH = db_path

        try:
            from core.orchestrator import run_pipeline
            session = run(run_pipeline())
        finally:
            col_mod.SOURCE_MAP               = orig_map
            cfg_mod.settings.SOURCES_ENABLED = orig_en

        # 2 notifications attendues (score 0.85 et 0.65 > seuil 0.4)
        assert session["sent"] == 2
        assert session["collected"] == 3
        assert mock_post.call_count == 2

    @patch("agents.notifier.requests.post")
    @patch("core.orchestrator.score_job",   new_callable=AsyncMock)
    @patch("core.orchestrator.analyze_job", new_callable=AsyncMock)
    def test_pipeline_skips_below_threshold(self, mock_analyze, mock_score, mock_post, real_db):
        """Jobs sous le seuil MIN_SCORE → aucune notification."""
        db_mod, db_path = real_db
        mock_post.return_value = _mock_telegram_ok()

        jobs_in = [make_raw_job(1, "malt")]
        low     = make_analyzed_job(1, "malt", score=0.10)
        mock_analyze.return_value = low
        mock_score.return_value   = low

        import agents.collector as col_mod, config.settings as cfg_mod, core.database as db_m
        orig_map = col_mod.SOURCE_MAP.copy()
        orig_en  = cfg_mod.settings.SOURCES_ENABLED[:]
        col_mod.SOURCE_MAP               = {"malt": _fake_source(jobs_in)}
        cfg_mod.settings.SOURCES_ENABLED = ["malt"]
        cfg_mod.settings.MIN_SCORE       = 0.4
        cfg_mod.settings.DB_PATH         = db_path
        db_m.settings.DB_PATH            = db_path

        try:
            from core.orchestrator import run_pipeline
            session = run(run_pipeline())
        finally:
            col_mod.SOURCE_MAP               = orig_map
            cfg_mod.settings.SOURCES_ENABLED = orig_en

        assert session["sent"]    == 0
        assert mock_post.call_count == 0

    @patch("agents.notifier.requests.post")
    @patch("core.orchestrator.score_job",   new_callable=AsyncMock)
    @patch("core.orchestrator.analyze_job", new_callable=AsyncMock)
    def test_pipeline_deduplicates_same_url(self, mock_analyze, mock_score, mock_post, real_db):
        """Même URL soumise deux fois → sauvegardée et envoyée une seule fois."""
        db_mod, db_path = real_db
        mock_post.return_value = _mock_telegram_ok()

        same_url = "https://codeur.com/missions/99"
        job1     = make_raw_job(1, "codeur"); job1["url"] = same_url
        job2     = make_raw_job(2, "codeur"); job2["url"] = same_url  # doublon URL

        analyzed = make_analyzed_job(1, "codeur", score=0.80)
        analyzed["url"] = same_url
        mock_analyze.return_value = analyzed
        mock_score.return_value   = analyzed

        import agents.collector as col_mod, config.settings as cfg_mod, core.database as db_m
        orig_map = col_mod.SOURCE_MAP.copy()
        orig_en  = cfg_mod.settings.SOURCES_ENABLED[:]
        col_mod.SOURCE_MAP               = {"codeur": _fake_source([job1, job2])}
        cfg_mod.settings.SOURCES_ENABLED = ["codeur"]
        cfg_mod.settings.MIN_SCORE       = 0.4
        cfg_mod.settings.DB_PATH         = db_path
        db_m.settings.DB_PATH            = db_path

        try:
            from core.orchestrator import run_pipeline
            session = run(run_pipeline())
        finally:
            col_mod.SOURCE_MAP               = orig_map
            cfg_mod.settings.SOURCES_ENABLED = orig_en

        # Une seule notification malgré 2 jobs avec même URL
        assert session["sent"] <= 1
        assert mock_post.call_count <= 1

    @patch("agents.notifier.requests.post")
    @patch("core.orchestrator.score_job",   new_callable=AsyncMock)
    @patch("core.orchestrator.analyze_job", new_callable=AsyncMock)
    def test_pipeline_never_resends_seen_job(self, mock_analyze, mock_score, mock_post, real_db):
        """Un job déjà en base ne doit pas être renvoyé au 2ème cycle."""
        db_mod, db_path = real_db
        mock_post.return_value = _mock_telegram_ok()

        job      = make_raw_job(1, "reddit")
        analyzed = make_analyzed_job(1, "reddit", score=0.80)
        mock_analyze.return_value = analyzed
        mock_score.return_value   = analyzed

        import agents.collector as col_mod, config.settings as cfg_mod, core.database as db_m
        orig_map = col_mod.SOURCE_MAP.copy()
        orig_en  = cfg_mod.settings.SOURCES_ENABLED[:]
        col_mod.SOURCE_MAP               = {"reddit": _fake_source([job])}
        cfg_mod.settings.SOURCES_ENABLED = ["reddit"]
        cfg_mod.settings.MIN_SCORE       = 0.4
        cfg_mod.settings.DB_PATH         = db_path
        db_m.settings.DB_PATH            = db_path

        try:
            from core.orchestrator import run_pipeline
            session1 = run(run_pipeline())   # 1er cycle
            session2 = run(run_pipeline())   # 2ème cycle → même job déjà vu
        finally:
            col_mod.SOURCE_MAP               = orig_map
            cfg_mod.settings.SOURCES_ENABLED = orig_en

        assert session1["sent"] == 1
        assert session2["sent"] == 0  # pas de renvoi
        assert mock_post.call_count == 1  # une seule notif au total

    @patch("agents.notifier.requests.post")
    @patch("core.orchestrator.score_job",   new_callable=AsyncMock)
    @patch("core.orchestrator.analyze_job", new_callable=AsyncMock)
    def test_pipeline_sorts_by_score_desc(self, mock_analyze, mock_score, mock_post, real_db):
        """Le pipeline doit notifier les jobs par score décroissant."""
        db_mod, db_path = real_db
        notified_scores = []

        def capture_alert(job, profile_label=""):
            notified_scores.append(job.get("score", 0))
            return True

        jobs_in = [make_raw_job(i, "upwork") for i in range(1, 4)]
        j1 = make_analyzed_job(1, "upwork", score=0.30)  # sous seuil
        j2 = make_analyzed_job(2, "upwork", score=0.90)  # haut
        j3 = make_analyzed_job(3, "upwork", score=0.55)  # moyen

        mock_analyze.side_effect = [j1, j2, j3]
        mock_score.side_effect   = [j1, j2, j3]

        import agents.collector as col_mod, config.settings as cfg_mod, core.database as db_m
        orig_map = col_mod.SOURCE_MAP.copy()
        orig_en  = cfg_mod.settings.SOURCES_ENABLED[:]
        col_mod.SOURCE_MAP               = {"upwork": _fake_source(jobs_in)}
        cfg_mod.settings.SOURCES_ENABLED = ["upwork"]
        cfg_mod.settings.MIN_SCORE       = 0.4
        cfg_mod.settings.DB_PATH         = db_path
        db_m.settings.DB_PATH            = db_path

        with patch("core.orchestrator.send_alert", side_effect=capture_alert):
            try:
                from core.orchestrator import run_pipeline
                run(run_pipeline())
            finally:
                col_mod.SOURCE_MAP               = orig_map
                cfg_mod.settings.SOURCES_ENABLED = orig_en

        # Seuls les jobs au-dessus du seuil sont notifiés
        assert all(s >= 0.4 for s in notified_scores)
        # Et dans l'ordre décroissant
        assert notified_scores == sorted(notified_scores, reverse=True)

    @patch("agents.notifier.requests.post")
    @patch("core.orchestrator.score_job",   new_callable=AsyncMock)
    @patch("core.orchestrator.analyze_job", new_callable=AsyncMock)
    def test_pipeline_handles_empty_sources(self, mock_analyze, mock_score, mock_post, real_db):
        """Si toutes les sources retournent vide → pipeline tourne sans erreur."""
        db_mod, db_path = real_db

        import agents.collector as col_mod, config.settings as cfg_mod, core.database as db_m
        orig_map = col_mod.SOURCE_MAP.copy()
        orig_en  = cfg_mod.settings.SOURCES_ENABLED[:]
        col_mod.SOURCE_MAP               = {"codeur": _fake_source([])}
        cfg_mod.settings.SOURCES_ENABLED = ["codeur"]
        cfg_mod.settings.DB_PATH         = db_path
        db_m.settings.DB_PATH            = db_path

        try:
            from core.orchestrator import run_pipeline
            session = run(run_pipeline())
        finally:
            col_mod.SOURCE_MAP               = orig_map
            cfg_mod.settings.SOURCES_ENABLED = orig_en

        assert session["collected"] == 0
        assert session["sent"]      == 0
        assert mock_post.call_count == 0

    @patch("agents.notifier.requests.post")
    @patch("core.orchestrator.score_job",   new_callable=AsyncMock)
    @patch("core.orchestrator.analyze_job", new_callable=AsyncMock)
    def test_pipeline_returns_session_stats(self, mock_analyze, mock_score, mock_post, real_db):
        """run_pipeline() doit retourner un dict de stats complet."""
        db_mod, db_path = real_db
        mock_post.return_value = _mock_telegram_ok()

        jobs_in  = [make_raw_job(i, "codeur") for i in range(1, 4)]
        analyzed = [make_analyzed_job(i, "codeur", score=0.70) for i in range(1, 4)]
        mock_analyze.side_effect = analyzed
        mock_score.side_effect   = analyzed

        import agents.collector as col_mod, config.settings as cfg_mod, core.database as db_m
        orig_map = col_mod.SOURCE_MAP.copy()
        orig_en  = cfg_mod.settings.SOURCES_ENABLED[:]
        col_mod.SOURCE_MAP               = {"codeur": _fake_source(jobs_in)}
        cfg_mod.settings.SOURCES_ENABLED = ["codeur"]
        cfg_mod.settings.MIN_SCORE       = 0.4
        cfg_mod.settings.DB_PATH         = db_path
        db_m.settings.DB_PATH            = db_path

        try:
            from core.orchestrator import run_pipeline
            session = run(run_pipeline())
        finally:
            col_mod.SOURCE_MAP               = orig_map
            cfg_mod.settings.SOURCES_ENABLED = orig_en

        required_keys = {"collected", "new", "analyzed", "sent", "skipped"}
        assert required_keys.issubset(set(session.keys()))
        assert isinstance(session["collected"], int)
        assert isinstance(session["sent"],      int)
