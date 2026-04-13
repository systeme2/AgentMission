# =============================================================
# tests/phase4/test_scoring_memory_analyzer.py
# =============================================================
#
# Tests approfondis du scorer, de la mémoire et de l'analyzer.
# On vérifie la logique métier : pertinence, consistance,
# bornage, apprentissage, fallback sans API key.
# =============================================================

import asyncio, pytest, json
from unittest.mock import patch, MagicMock
from tests.phase4.conftest import make_raw_job, make_analyzed_job, run


# ═══════════════════════════════════════════════════════════════
# SCORER
# ═══════════════════════════════════════════════════════════════

class TestScorerLogic:

    def _score(self, job):
        return run(self._score_async(job))

    async def _score_async(self, job):
        from agents.scorer import score_job
        return await score_job(job)

    def test_score_range_0_to_1(self):
        """Le score doit toujours être entre 0.0 et 1.0."""
        from agents.scorer import score_job
        job = make_analyzed_job(1, score=0.5)
        result = run(score_job(job))
        assert 0.0 <= result["score"] <= 1.0

    def test_score_wordpress_job_high(self):
        """Un job WordPress doit scorer haut (keyword préféré)."""
        from agents.scorer import score_job
        job = make_raw_job(1)
        job["title"]       = "Développeur WordPress senior freelance"
        job["description"] = "Refonte site WordPress, remote, budget 800€"
        job["analysis"] = {
            "stack": ["wordpress"], "budget_estime": 800,
            "remote": True, "est_freelance": True, "langue": "fr",
        }
        result = run(score_job(job))
        assert result["score"] >= 0.4, f"Score trop bas pour WordPress freelance: {result['score']}"

    def test_score_negative_keyword_penalizes(self):
        """Un job avec mot-clé négatif doit avoir un score réduit."""
        from agents.scorer import score_job
        from config.settings import settings

        job_pos = make_raw_job(1)
        job_pos["title"] = "Développeur React freelance"
        job_pos["analysis"] = {"stack": ["react"], "budget_estime": 500,
                                "remote": True, "est_freelance": True, "langue": "fr"}

        job_neg = make_raw_job(2)
        job_neg["title"] = "Développeur stagiaire bénévole cobol"
        job_neg["analysis"] = {"stack": ["cobol"], "budget_estime": 0,
                                "remote": False, "est_freelance": False, "langue": "fr"}

        result_pos = run(score_job(job_pos))
        result_neg = run(score_job(job_neg))
        assert result_pos["score"] > result_neg["score"]

    def test_score_remote_boosts(self):
        """Remote=True doit booster le score."""
        from agents.scorer import score_job

        job_remote = make_raw_job(1)
        job_remote["analysis"] = {"stack": [], "budget_estime": 400,
                                   "remote": True, "est_freelance": True, "langue": "fr"}

        job_onsite = make_raw_job(2)
        job_onsite["analysis"] = {"stack": [], "budget_estime": 400,
                                   "remote": False, "est_freelance": True, "langue": "fr"}

        r1 = run(score_job(job_remote))
        r2 = run(score_job(job_onsite))
        assert r1["score"] > r2["score"]

    def test_score_high_budget_boosts(self):
        """Budget élevé doit donner un score plus haut."""
        from agents.scorer import score_job
        from config.settings import settings

        job_rich = make_raw_job(1)
        job_rich["analysis"] = {"stack": [], "budget_estime": settings.MIN_BUDGET * 3,
                                  "remote": False, "est_freelance": True, "langue": "fr"}

        job_poor = make_raw_job(2)
        job_poor["analysis"] = {"stack": [], "budget_estime": 0,
                                  "remote": False, "est_freelance": True, "langue": "fr"}

        r1 = run(score_job(job_rich))
        r2 = run(score_job(job_poor))
        assert r1["score"] >= r2["score"]

    def test_score_not_freelance_penalizes(self):
        """est_freelance=False doit réduire le score."""
        from agents.scorer import score_job

        job_fl = make_raw_job(1)
        job_fl["analysis"] = {"stack": ["react"], "budget_estime": 500,
                               "remote": True, "est_freelance": True, "langue": "fr"}

        job_cdi = make_raw_job(2)
        job_cdi["analysis"] = {"stack": ["react"], "budget_estime": 500,
                                "remote": True, "est_freelance": False, "langue": "fr"}

        r1 = run(score_job(job_fl))
        r2 = run(score_job(job_cdi))
        assert r1["score"] > r2["score"]

    def test_score_detail_returned(self):
        """Le dictionnaire score_detail doit être présent et complet."""
        from agents.scorer import score_job
        job = make_analyzed_job(1, score=0.5)
        result = run(score_job(job))
        assert "score_detail" in result
        detail = result["score_detail"]
        assert "keywords" in detail
        assert "budget"   in detail
        assert "remote"   in detail

    def test_score_consistency(self):
        """Même job → même score à chaque appel (déterminisme)."""
        from agents.scorer import score_job
        job1 = make_analyzed_job(1, "codeur", 0.5)
        job2 = make_analyzed_job(1, "codeur", 0.5)
        r1 = run(score_job(job1))
        r2 = run(score_job(job2))
        assert r1["score"] == r2["score"]

    def test_score_final_bounded_after_memory(self):
        """Le score final doit rester dans [0, 1] même après ajustement mémoire."""
        from agents.scorer import score_job
        with patch("agents.scorer.apply_memory_to_score", return_value=999.0):
            job = make_analyzed_job(1)
            result = run(score_job(job))
            assert result["score"] <= 1.0

        with patch("agents.scorer.apply_memory_to_score", return_value=-999.0):
            job = make_analyzed_job(1)
            result = run(score_job(job))
            assert result["score"] >= 0.0


# ═══════════════════════════════════════════════════════════════
# MEMORY
# ═══════════════════════════════════════════════════════════════

class TestMemorySystem:

    @pytest.fixture
    def db(self, tmp_path):
        import core.database as db_mod, core.memory as mem_mod
        original_db  = db_mod.settings.DB_PATH
        original_mem = mem_mod.settings if hasattr(mem_mod, 'settings') else None
        db_mod.settings.DB_PATH = str(tmp_path / "mem_test.db")
        db_mod.init_db()
        yield db_mod, mem_mod
        db_mod.settings.DB_PATH = original_db

    def test_get_preferences_returns_dict(self, db):
        _, mem_mod = db
        prefs = mem_mod.get_preferences()
        assert isinstance(prefs, dict)
        assert "liked_keywords"   in prefs
        assert "disliked_keywords" in prefs

    def test_record_like_updates_preferences(self, db):
        db_mod, mem_mod = db
        job = make_analyzed_job(1, "codeur", 0.7)
        job["title"] = "Expert WordPress React freelance"
        mem_mod.record_like(job)
        prefs = mem_mod.get_preferences()
        liked = prefs.get("liked_keywords", [])
        # Au moins un des mots du titre doit être dans liked
        assert len(liked) > 0

    def test_record_dislike_updates_preferences(self, db):
        _, mem_mod = db
        job = make_analyzed_job(1, "codeur", 0.1)
        job["title"] = "Développeur COBOL legacy urgent"
        mem_mod.record_dislike(job)
        prefs = mem_mod.get_preferences()
        disliked = prefs.get("disliked_keywords", [])
        assert len(disliked) > 0

    def test_like_boosts_future_score(self, db):
        """Après un like sur un mot-clé, le score de jobs similaires augmente."""
        db_mod, mem_mod = db
        job = make_analyzed_job(1)
        job["title"] = "Mission Laravel freelance Paris"

        # Score avant like
        score_before = mem_mod.apply_memory_to_score(job, 0.5)

        # Enregistre le like
        mem_mod.record_like(job)

        # Score après like
        score_after = mem_mod.apply_memory_to_score(job, 0.5)

        assert score_after >= score_before

    def test_dislike_reduces_future_score(self, db):
        """Après un dislike, le score de jobs similaires baisse."""
        db_mod, mem_mod = db
        job = make_analyzed_job(1)
        job["title"] = "Développeur PHP legacy maintenance"

        score_before = mem_mod.apply_memory_to_score(job, 0.5)
        mem_mod.record_dislike(job)
        score_after = mem_mod.apply_memory_to_score(job, 0.5)

        assert score_after <= score_before

    def test_apply_memory_bounded(self, db):
        """Le score ajusté par la mémoire reste entre 0 et 1."""
        _, mem_mod = db
        job = make_analyzed_job(1)
        for base in [0.0, 0.5, 1.0]:
            result = mem_mod.apply_memory_to_score(job, base)
            assert 0.0 <= result <= 1.0, f"Score hors bornes: {result}"

    def test_preferences_limited_to_100(self, db):
        """La liste liked_keywords ne doit pas dépasser 100 entrées."""
        _, mem_mod = db
        for i in range(120):
            job = make_analyzed_job(i)
            job["title"] = f"tech_{i} unique_term_{i} freelance remote"
            mem_mod.record_like(job)
        prefs = mem_mod.get_preferences()
        assert len(prefs.get("liked_keywords", [])) <= 100


# ═══════════════════════════════════════════════════════════════
# ANALYZER
# ═══════════════════════════════════════════════════════════════

class TestAnalyzerFallback:
    """Tests de l'analyzer sans clé OpenAI (fallback mots-clés)."""

    def test_basic_analysis_detects_stack(self):
        """L'analyse basique détecte les technos dans le titre/description."""
        from agents.analyzer import _basic_analysis
        job = make_raw_job(1)
        job["title"]       = "Développeur React + WordPress"
        job["description"] = "Mission React NextJS SEO remote"
        analysis = _basic_analysis(job)
        assert "react" in analysis["stack"] or "wordpress" in analysis["stack"]

    def test_basic_analysis_detects_remote(self):
        from agents.analyzer import _basic_analysis
        job = make_raw_job(1)
        job["description"] = "Full remote, télétravail complet"
        analysis = _basic_analysis(job)
        assert analysis["remote"] is True

    def test_basic_analysis_extracts_budget(self):
        from agents.analyzer import _basic_analysis
        job = make_raw_job(1)
        job["description"] = "Budget: 800€ pour la mission"
        analysis = _basic_analysis(job)
        assert analysis["budget_estime"] == 800

    def test_basic_analysis_returns_required_fields(self):
        from agents.analyzer import _basic_analysis
        job     = make_raw_job(1)
        result  = _basic_analysis(job)
        required = {"type", "stack", "budget_estime", "niveau", "remote",
                    "resume", "est_freelance", "langue"}
        assert required.issubset(set(result.keys()))

    def test_extract_budget_various_formats(self):
        from agents.analyzer import _extract_budget
        assert _extract_budget("Budget 500€")    == 500
        assert _extract_budget("$800 project")   == 800
        assert _extract_budget("budget: 1200 euros") == 1200
        assert _extract_budget("no budget here") == 0

    async def _analyze(self, job):
        from agents.analyzer import analyze_job
        return await analyze_job(job)

    def test_analyze_job_uses_fallback_without_api_key(self):
        """Sans clé OpenAI, analyze_job utilise _basic_analysis."""
        from config.settings import settings
        original = settings.OPENAI_API_KEY
        settings.OPENAI_API_KEY = "sk-..."  # valeur par défaut = pas de clé
        try:
            job    = make_raw_job(1)
            result = run(self._analyze(job))
            assert "analysis" in result
            assert isinstance(result["analysis"], dict)
        finally:
            settings.OPENAI_API_KEY = original

    def test_analyze_job_handles_openai_error(self):
        """Si l'API OpenAI est configurée mais retourne une erreur → fallback."""
        from config.settings import settings
        settings.OPENAI_API_KEY = "sk-real-but-mock"
        try:
            with patch("agents.analyzer.openai.chat.completions.create",
                       side_effect=Exception("API Error")):
                job    = make_raw_job(1)
                result = run(self._analyze(job))
                assert "analysis" in result
                assert isinstance(result["analysis"], dict)
        finally:
            settings.OPENAI_API_KEY = "sk-..."

    def test_analyze_job_handles_invalid_json_from_openai(self):
        """Si OpenAI retourne du JSON invalide → fallback gracieux."""
        from config.settings import settings
        settings.OPENAI_API_KEY = "sk-real-but-mock"
        try:
            mock_response = MagicMock()
            mock_response.choices[0].message.content = "NOT VALID JSON {{"
            with patch("agents.analyzer.openai.chat.completions.create",
                       return_value=mock_response):
                job    = make_raw_job(1)
                result = run(self._analyze(job))
                assert "analysis" in result
        finally:
            settings.OPENAI_API_KEY = "sk-..."
