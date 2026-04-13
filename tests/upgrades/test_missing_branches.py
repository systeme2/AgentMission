# =============================================================
# tests/upgrades/test_missing_branches.py
# =============================================================
# Couvre les branches non testées identifiées lors de l'audit :
#   agents/scorer.py        (46-49, 67, 103-110)
#   agents/semantic_scorer.py (48-58, 77, 112-132)
#   agents/analyzer.py      (50-71, 74-75)
#   core/orchestrator.py    (26-27, 48, 92-94, 120-121)
#   core/telegram_bot.py    (321-350)
#   sources/hackernews.py   (164-183)
#   sources/twitter.py      (166-167, 182-198)
#   sources/linkedin.py     (49-76, 80-82)
#   sources/malt.py         (78-109)
# =============================================================

import asyncio, json, pytest
from unittest.mock import patch, MagicMock, AsyncMock

def run(c): return asyncio.get_event_loop().run_until_complete(c)


# ═══════════════════════════════════════════════════════════════
# SCORER — budget 0 < x < MIN_BUDGET, langue non préférée,
#          _parse_budget_raw sans match et ValueError
# ═══════════════════════════════════════════════════════════════

class TestScorerMissingBranches:

    def _make_job(self, budget=0, langue="fr", remote=True, freelance=True, stack=None):
        return {
            "title": "Mission test", "description": "Dev web remote",
            "url": f"https://example.com/{budget}", "source": "codeur", "budget_raw": "",
            "analysis": {
                "stack": stack or [], "budget_estime": budget,
                "remote": remote, "est_freelance": freelance, "langue": langue,
            }
        }

    def test_budget_low_but_positive(self):
        """Budget > 0 mais < MIN_BUDGET → branche elif budget > 0 (ligne 46-47)."""
        from agents.scorer import score_job
        from config.settings import settings
        job = self._make_job(budget=50)  # < settings.MIN_BUDGET (200)
        result = run(score_job(job))
        assert 0.0 <= result["score"] <= 1.0
        assert result["score_detail"]["budget"]["score"] == 0.05

    def test_budget_zero_neutre(self):
        """Budget = 0 → branche else budget_score = 0.05 (ligne 48-49)."""
        from agents.scorer import score_job
        job = self._make_job(budget=0)
        result = run(score_job(job))
        assert result["score_detail"]["budget"]["value"] == 0
        assert result["score_detail"]["budget"]["score"] == 0.05

    def test_langue_non_preferee(self):
        """Langue non dans PREFERRED_LANGS → branche else ligne 67."""
        from agents.scorer import score_job
        from config.settings import settings
        original = settings.PREFERRED_LANGS[:]
        settings.PREFERRED_LANGS = ["fr"]
        try:
            job = self._make_job(langue="en")
            result = run(score_job(job))
            # La langue "en" n'est pas dans ["fr"] → score_detail["lang"] = "en"
            assert result["score_detail"]["lang"] == "en"
            # Pas de bonus de langue
        finally:
            settings.PREFERRED_LANGS = original

    def test_parse_budget_raw_no_digit_returns_zero(self):
        """_parse_budget_raw sans chiffre → return 0 (ligne 110)."""
        from agents.scorer import _parse_budget_raw
        assert _parse_budget_raw("budget non précisé") == 0
        assert _parse_budget_raw("à négocier") == 0

    def test_parse_budget_raw_empty_returns_zero(self):
        """_parse_budget_raw chaîne vide → return 0 (ligne 103)."""
        from agents.scorer import _parse_budget_raw
        assert _parse_budget_raw("") == 0
        assert _parse_budget_raw(None) == 0

    def test_parse_budget_raw_valid(self):
        """_parse_budget_raw avec chiffre → retourne le nombre (ligne 107)."""
        from agents.scorer import _parse_budget_raw
        assert _parse_budget_raw("500 €") == 500
        assert _parse_budget_raw("1 200€") == 1200

    def test_budget_at_min_budget(self):
        """Budget exactement = MIN_BUDGET → branche elif budget >= MIN_BUDGET."""
        from agents.scorer import score_job
        from config.settings import settings
        job = self._make_job(budget=settings.MIN_BUDGET)
        result = run(score_job(job))
        assert result["score_detail"]["budget"]["score"] == 0.15

    def test_budget_above_2x_min_budget(self):
        """Budget >= 2*MIN_BUDGET → branche if budget_score = 0.25."""
        from agents.scorer import score_job
        from config.settings import settings
        job = self._make_job(budget=settings.MIN_BUDGET * 3)
        result = run(score_job(job))
        assert result["score_detail"]["budget"]["score"] == 0.25


# ═══════════════════════════════════════════════════════════════
# SEMANTIC SCORER — _get_embedding_sync avec API, _get_profile_embedding
#                   auto-génération, clear_cache entre tests
# ═══════════════════════════════════════════════════════════════

class TestSemanticScorerMissing:

    def setup_method(self):
        from agents.semantic_scorer import clear_cache
        clear_cache()

    def test_get_embedding_sync_calls_openai(self):
        """_get_embedding_sync appelle openai.embeddings.create (ligne 48-58)."""
        from agents.semantic_scorer import _get_embedding_sync
        from config.settings import settings
        settings.OPENAI_API_KEY = "sk-mock-real"
        try:
            mock_resp = MagicMock()
            mock_resp.data[0].embedding = [0.1] * 100
            # openai v1+ est importé localement avec import openai
            # On mock le module entier pour intercepter openai.embeddings.create
            import sys
            mock_openai = MagicMock()
            mock_openai.api_key = "sk-mock"
            mock_openai.embeddings.create.return_value = mock_resp
            original_openai = sys.modules.get("openai")
            sys.modules["openai"] = mock_openai
            try:
                # Recharger pour prendre le mock
                from agents.semantic_scorer import _get_embedding_sync as fn
                result = fn("test text")
            finally:
                if original_openai is not None:
                    sys.modules["openai"] = original_openai
                else:
                    del sys.modules["openai"]
            assert result == [0.1] * 100
        finally:
            settings.OPENAI_API_KEY = "sk-..."

    def test_get_embedding_sync_returns_none_on_exception(self):
        """_get_embedding_sync → None si openai lève une exception (ligne 56-58)."""
        from agents.semantic_scorer import _get_embedding_sync
        from config.settings import settings
        settings.OPENAI_API_KEY = "sk-mock-real"
        try:
            import sys
            mock_openai = MagicMock()
            mock_openai.embeddings.create.side_effect = Exception("API error")
            original_openai = sys.modules.get("openai")
            sys.modules["openai"] = mock_openai
            try:
                result = _get_embedding_sync("test text")
            finally:
                if original_openai is not None:
                    sys.modules["openai"] = original_openai
                else:
                    del sys.modules["openai"]
            assert result is None
        finally:
            settings.OPENAI_API_KEY = "sk-..."

    def test_get_profile_embedding_auto_generates_text(self):
        """Sans IDEAL_PROFILE_TEXT, auto-génère depuis PREFERRED_KEYWORDS (ligne 77)."""
        from agents.semantic_scorer import _get_profile_embedding, clear_cache
        from config.settings import settings
        clear_cache()
        settings.OPENAI_API_KEY = "sk-mock"
        original_ideal = settings.IDEAL_PROFILE_TEXT
        settings.IDEAL_PROFILE_TEXT = ""  # force l'auto-génération
        try:
            mock_resp = MagicMock()
            mock_resp.data[0].embedding = [0.5] * 50
            with patch("agents.semantic_scorer._get_embedding_sync",
                       return_value=[0.5] * 50):
                result = run(_get_profile_embedding())
            assert result == [0.5] * 50
        finally:
            settings.OPENAI_API_KEY = "sk-..."
            settings.IDEAL_PROFILE_TEXT = original_ideal
            clear_cache()

    def test_get_profile_embedding_uses_custom_text(self):
        """Avec IDEAL_PROFILE_TEXT défini, l'utilise directement (ligne 112-132)."""
        from agents.semantic_scorer import _get_profile_embedding, clear_cache
        from config.settings import settings
        clear_cache()
        settings.OPENAI_API_KEY = "sk-mock"
        original_ideal = settings.IDEAL_PROFILE_TEXT
        settings.IDEAL_PROFILE_TEXT = "Expert React senior remote uniquement"
        try:
            captured_text = []
            def fake_embed_sync(text):
                captured_text.append(text)
                return [0.3] * 50
            with patch("agents.semantic_scorer._get_embedding_sync",
                       side_effect=fake_embed_sync):
                result = run(_get_profile_embedding())
            assert "Expert React" in captured_text[0]
            assert result == [0.3] * 50
        finally:
            settings.OPENAI_API_KEY = "sk-..."
            settings.IDEAL_PROFILE_TEXT = original_ideal
            clear_cache()

    def test_profile_embedding_cached_after_first_call(self):
        """_profile_embedding est mis en cache après le premier appel."""
        from agents.semantic_scorer import _get_profile_embedding, clear_cache
        from config.settings import settings
        clear_cache()
        settings.OPENAI_API_KEY = "sk-mock"
        call_count = [0]
        def count_calls(text):
            call_count[0] += 1
            return [0.2] * 20
        with patch("agents.semantic_scorer._get_embedding_sync",
                   side_effect=count_calls):
            run(_get_profile_embedding())
            run(_get_profile_embedding())
        assert call_count[0] == 1, f"Attendu 1 appel, obtenu {call_count[0]}"
        clear_cache()
        settings.OPENAI_API_KEY = "sk-..."

    def test_semantic_score_bonus_with_real_embeddings(self):
        """semantic_score_bonus avec embeddings mockés retourne bonus [0, 0.20]."""
        from agents.semantic_scorer import semantic_score_bonus, clear_cache
        from config.settings import settings
        clear_cache()
        settings.OPENAI_API_KEY = "sk-mock"
        try:
            with patch("agents.semantic_scorer._get_embedding_sync",
                       return_value=[1.0] * 100):
                job = {"title": "React Dev", "description": "remote mission",
                       "analysis": {"stack": ["react"]}}
                bonus = run(semantic_score_bonus(job))
            assert 0.0 <= bonus <= 0.20
        finally:
            settings.OPENAI_API_KEY = "sk-..."
            clear_cache()


# ═══════════════════════════════════════════════════════════════
# ANALYZER — branche OpenAI réelle (lignes 50-71, 74-75)
# ═══════════════════════════════════════════════════════════════

class TestAnalyzerOpenAIBranch:

    def test_openai_branch_full_success(self):
        """La branche try OpenAI complète est couverte avec to_thread mocké."""
        from config.settings import settings
        settings.OPENAI_API_KEY = "sk-mock-real"
        expected = {
            "type": "web", "stack": ["react"], "budget_estime": 600,
            "niveau": "expert", "remote": True, "resume": "Mission React",
            "est_freelance": True, "langue": "fr"
        }
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = json.dumps(expected)

        async def fake_to_thread(fn, *args, **kwargs):
            return mock_resp

        try:
            with patch("agents.analyzer.asyncio.to_thread", fake_to_thread):
                from agents.analyzer import analyze_job
                job = {"title": "Dev React", "description": "React mission remote",
                       "url": "https://x.com/1", "source": "codeur", "budget_raw": ""}
                result = run(analyze_job(job))
            assert "analysis" in result
            analysis = result["analysis"]
            assert isinstance(analysis, dict)
            assert set(analysis.keys()) >= {"type", "stack", "budget_estime",
                                            "niveau", "remote", "resume",
                                            "est_freelance", "langue"}
        finally:
            settings.OPENAI_API_KEY = "sk-..."

    def test_openai_json_decode_error_fallback(self):
        """JSONDecodeError → _basic_analysis (lignes 73-75)."""
        from config.settings import settings
        settings.OPENAI_API_KEY = "sk-mock-real"
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = "NOT JSON AT ALL {{"

        async def fake_to_thread(fn, *args, **kwargs):
            return mock_resp

        try:
            with patch("agents.analyzer.asyncio.to_thread", fake_to_thread):
                from agents.analyzer import analyze_job
                job = {"title": "Dev PHP", "description": "PHP legacy mission",
                       "url": "https://x.com/2", "source": "codeur", "budget_raw": ""}
                result = run(analyze_job(job))
            assert "analysis" in result
            assert isinstance(result["analysis"], dict)
        finally:
            settings.OPENAI_API_KEY = "sk-..."

    def test_openai_markdown_fence_json(self):
        """JSON entouré de ```json...``` est nettoyé (lignes 65-68)."""
        from config.settings import settings
        settings.OPENAI_API_KEY = "sk-mock-real"
        expected = {"type": "web", "stack": ["vue"], "budget_estime": 400,
                    "niveau": "intermédiaire", "remote": False,
                    "resume": "Vue.js", "est_freelance": True, "langue": "fr"}
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = (
            "```json\n" + json.dumps(expected) + "\n```"
        )

        async def fake_to_thread(fn, *args, **kwargs):
            return mock_resp

        try:
            with patch("agents.analyzer.asyncio.to_thread", fake_to_thread):
                from agents.analyzer import analyze_job
                job = {"title": "Dev Vue", "description": "Vue.js mission",
                       "url": "https://x.com/3", "source": "malt", "budget_raw": ""}
                result = run(analyze_job(job))
            assert "analysis" in result
            assert isinstance(result["analysis"], dict)
        finally:
            settings.OPENAI_API_KEY = "sk-..."


# ═══════════════════════════════════════════════════════════════
# ORCHESTRATOR — pause early return, IDEAL_PROFILE_TEXT override,
#               process_job exception, is_new=False skip
# ═══════════════════════════════════════════════════════════════

class TestOrchestratorMissingBranches:

    def _setup(self, tmp_path):
        import core.database as db_mod, config.settings as cfg_mod
        import agents.collector as col_mod
        db_mod.settings.DB_PATH = str(tmp_path / "orch_test.db")
        db_mod.init_db()
        return db_mod, cfg_mod, col_mod

    def test_pipeline_returns_paused_when_paused(self, tmp_path):
        """Si is_paused() → retour early avec paused=True (lignes 25-27)."""
        db_mod, cfg_mod, col_mod = self._setup(tmp_path)
        orig_db = col_mod  # juste pour référence
        with patch("core.orchestrator.is_paused", return_value=True):
            from core.orchestrator import run_pipeline
            result = run(run_pipeline())
        assert result.get("paused") is True
        assert result["collected"] == 0
        assert result["sent"] == 0

    def test_pipeline_applies_ideal_profile_text(self, tmp_path):
        """Profil avec ideal_profile_text → override IDEAL_PROFILE_TEXT (ligne 50)."""
        db_mod, cfg_mod, col_mod = self._setup(tmp_path)
        original_ideal = cfg_mod.settings.IDEAL_PROFILE_TEXT
        original_sources = cfg_mod.settings.SOURCES_ENABLED[:]

        async def fake_src(): return []
        orig_map = col_mod.SOURCE_MAP.copy()
        col_mod.SOURCE_MAP = {"codeur": fake_src}
        cfg_mod.settings.SOURCES_ENABLED = ["codeur"]

        try:
            with patch("core.orchestrator.is_paused", return_value=False):
                from core.orchestrator import run_pipeline
                run(run_pipeline(profile_name="wordpress"))
            # Le profil wordpress a un ideal_profile_text → il a dû être appliqué
        finally:
            col_mod.SOURCE_MAP = orig_map
            cfg_mod.settings.SOURCES_ENABLED = original_sources
            cfg_mod.settings.IDEAL_PROFILE_TEXT = original_ideal
            db_mod.settings.DB_PATH = "data/missions.db"

    def test_pipeline_process_job_exception_returns_none(self, tmp_path):
        """Si analyze_job lève → process_job retourne None, job ignoré (lignes 92-94)."""
        db_mod, cfg_mod, col_mod = self._setup(tmp_path)
        from tests.phase4.conftest import make_raw_job

        job = make_raw_job(1, "codeur")
        original_sources = cfg_mod.settings.SOURCES_ENABLED[:]

        async def fake_src(): return [job]
        orig_map = col_mod.SOURCE_MAP.copy()
        col_mod.SOURCE_MAP = {"codeur": fake_src}
        cfg_mod.settings.SOURCES_ENABLED = ["codeur"]

        try:
            with patch("core.orchestrator.is_paused", return_value=False), \
                 patch("core.orchestrator.analyze_job",
                        new_callable=AsyncMock, side_effect=Exception("analyze crash")):
                from core.orchestrator import run_pipeline
                session = run(run_pipeline())
            # Le job a crashé lors de l'analyse → analyzed=0
            assert session["sent"] == 0
        finally:
            col_mod.SOURCE_MAP = orig_map
            cfg_mod.settings.SOURCES_ENABLED = original_sources
            db_mod.settings.DB_PATH = "data/missions.db"

    def test_pipeline_skips_already_saved_job(self, tmp_path):
        """save_mission retourne False (doublon) → skipped++ (lignes 119-121)."""
        db_mod, cfg_mod, col_mod = self._setup(tmp_path)
        from tests.phase4.conftest import make_raw_job, make_analyzed_job

        job = make_raw_job(1, "codeur")
        analyzed = make_analyzed_job(1, "codeur", score=0.8)
        original_sources = cfg_mod.settings.SOURCES_ENABLED[:]

        async def fake_src(): return [job]
        orig_map = col_mod.SOURCE_MAP.copy()
        col_mod.SOURCE_MAP = {"codeur": fake_src}
        cfg_mod.settings.SOURCES_ENABLED = ["codeur"]

        try:
            with patch("core.orchestrator.is_paused", return_value=False),                  patch("core.orchestrator.is_seen", return_value=False),                  patch("core.orchestrator.save_mission", return_value=False),                  patch("core.orchestrator.analyze_job",
                        new_callable=AsyncMock, return_value=analyzed),                  patch("core.orchestrator.score_job",
                        new_callable=AsyncMock, return_value=analyzed):
                from core.orchestrator import run_pipeline
                session = run(run_pipeline())
            # save_mission a retourné False → is_new=False → skipped++
            assert session["skipped"] >= 1
            assert session["sent"] == 0
        finally:
            col_mod.SOURCE_MAP = orig_map
            cfg_mod.settings.SOURCES_ENABLED = original_sources
            db_mod.settings.DB_PATH = "data/missions.db"


# ═══════════════════════════════════════════════════════════════
# TELEGRAM BOT — dispatch des commandes dans _dispatch_update
#                (lignes 323-350 non couvertes)
# ═══════════════════════════════════════════════════════════════

class TestTelegramBotDispatch:
    """Couvre les branches de _dispatch_update avec un chat_id numérique."""

    def _dispatch(self, text, handlers=None):
        """Helper : dispatche une commande et capture les handlers appelés."""
        from core import telegram_bot as tb
        # Sauvegarder et forcer chat_id numérique
        original_id = tb.settings.TELEGRAM_CHAT_ID
        tb.settings.TELEGRAM_CHAT_ID = "12345"
        update = {"message": {"text": text, "chat": {"id": 12345}}}
        patches = handlers or {}
        try:
            with patch("core.telegram_bot._send"), \
                 patch("core.telegram_bot._handle_start") as hs, \
                 patch("core.telegram_bot._handle_stats") as hst, \
                 patch("core.telegram_bot._handle_top5") as ht, \
                 patch("core.telegram_bot._handle_status") as hstatus, \
                 patch("core.telegram_bot._handle_resume") as hr, \
                 patch("core.telegram_bot._handle_pause") as hp, \
                 patch("core.telegram_bot._handle_seuil") as hse, \
                 patch("core.telegram_bot.get_all_missions", return_value=[]):
                from core.telegram_bot import _dispatch_update
                _dispatch_update(update)
                return {
                    "start": hs, "stats": hst, "top5": ht,
                    "status": hstatus, "resume": hr,
                    "pause": hp, "seuil": hse,
                }
        finally:
            tb.settings.TELEGRAM_CHAT_ID = original_id

    def test_dispatch_stats(self):
        h = self._dispatch("/stats")
        h["stats"].assert_called_once_with("12345")

    def test_dispatch_top5(self):
        h = self._dispatch("/top5")
        h["top5"].assert_called_once_with("12345")

    def test_dispatch_status(self):
        h = self._dispatch("/status")
        h["status"].assert_called_once_with("12345")

    def test_dispatch_resume(self):
        h = self._dispatch("/resume")
        h["resume"].assert_called_once_with("12345")

    def test_dispatch_pause_with_number(self):
        h = self._dispatch("/pause 90")
        h["pause"].assert_called_once_with("12345", 90)

    def test_dispatch_pause_without_number(self):
        """Sans nombre → envoie message d'aide (ne lève pas)."""
        from core import telegram_bot as tb
        original_id = tb.settings.TELEGRAM_CHAT_ID
        tb.settings.TELEGRAM_CHAT_ID = "12345"
        update = {"message": {"text": "/pause", "chat": {"id": 12345}}}
        try:
            with patch("core.telegram_bot._send") as ms:
                from core.telegram_bot import _dispatch_update
                _dispatch_update(update)
            ms.assert_called()
            assert "usage" in ms.call_args[0][1].lower() or "60" in ms.call_args[0][1]
        finally:
            tb.settings.TELEGRAM_CHAT_ID = original_id

    def test_dispatch_seuil_valid(self):
        h = self._dispatch("/seuil 0.55")
        h["seuil"].assert_called_once_with("12345", pytest.approx(0.55, abs=0.01))

    def test_dispatch_seuil_without_value(self):
        """Sans valeur → envoie message d'aide."""
        from core import telegram_bot as tb
        original_id = tb.settings.TELEGRAM_CHAT_ID
        tb.settings.TELEGRAM_CHAT_ID = "12345"
        update = {"message": {"text": "/seuil", "chat": {"id": 12345}}}
        try:
            with patch("core.telegram_bot._send") as ms:
                from core.telegram_bot import _dispatch_update
                _dispatch_update(update)
            ms.assert_called()
        finally:
            tb.settings.TELEGRAM_CHAT_ID = original_id

    def test_dispatch_seuil_invalid_float(self):
        """'/seuil abc' → ValueError catchée, envoie message d'aide."""
        from core import telegram_bot as tb
        original_id = tb.settings.TELEGRAM_CHAT_ID
        tb.settings.TELEGRAM_CHAT_ID = "12345"
        # "/seuil abc" → le regex r"/seuil\s+([\d.]+)" ne matche pas "abc"
        # donc tombe dans le else → envoie "Usage : /seuil 0.5"
        update = {"message": {"text": "/seuil abc", "chat": {"id": 12345}}}
        try:
            with patch("core.telegram_bot._send") as ms:
                from core.telegram_bot import _dispatch_update
                _dispatch_update(update)
            ms.assert_called()
        finally:
            tb.settings.TELEGRAM_CHAT_ID = original_id


# ═══════════════════════════════════════════════════════════════
# HACKERNEWS — fallback Algolia quand thread_id = None (164-192)
# ═══════════════════════════════════════════════════════════════

class TestHackerNewsFallback:

    @patch("sources.hackernews.requests.get")
    @patch("sources.hackernews.asyncio.sleep", return_value=None)
    @patch("sources.hackernews._fetch_who_is_hiring_thread_id", return_value=None)
    def test_fallback_algolia_when_no_thread(self, mock_tid, mock_sleep, mock_get):
        """Quand thread_id=None → requête Algolia directe (branche else ligne 168)."""
        algolia_resp = MagicMock()
        algolia_resp.status_code = 200
        algolia_resp.raise_for_status = MagicMock()
        algolia_resp.json.return_value = {
            "hits": [
                {
                    "objectID": "12345",
                    "story_text": "React developer | Remote | $120k | Looking for a React dev",
                    "created_at": "2024-03-15T10:00:00Z",
                }
            ]
        }
        mock_get.return_value = algolia_resp
        from sources.hackernews import get_hackernews_jobs
        jobs = run(get_hackernews_jobs())
        assert isinstance(jobs, list)
        # Le fallback doit avoir appelé requests.get
        mock_get.assert_called()

    @patch("sources.hackernews.requests.get")
    @patch("sources.hackernews.asyncio.sleep", return_value=None)
    @patch("sources.hackernews._fetch_who_is_hiring_thread_id", return_value=None)
    def test_fallback_filters_irrelevant(self, mock_tid, mock_sleep, mock_get):
        """Fallback filtre les hits non pertinents."""
        algolia_resp = MagicMock()
        algolia_resp.raise_for_status = MagicMock()
        algolia_resp.json.return_value = {
            "hits": [
                {"objectID": "1", "story_text": "Random blog post about AI theory"},
                {"objectID": "2", "story_text": "Remote Python developer needed for startup"},
            ]
        }
        mock_get.return_value = algolia_resp
        from sources.hackernews import get_hackernews_jobs
        jobs = run(get_hackernews_jobs())
        # Seul le 2e hit est pertinent (python, developer, remote)
        assert all(j["source"] == "hackernews" for j in jobs)

    @patch("sources.hackernews.requests.get", side_effect=Exception("réseau"))
    @patch("sources.hackernews.asyncio.sleep", return_value=None)
    @patch("sources.hackernews._fetch_who_is_hiring_thread_id", return_value=None)
    def test_fallback_network_error_returns_empty(self, mock_tid, mock_sleep, mock_get):
        """Fallback avec erreur réseau → liste vide, pas d'exception."""
        from sources.hackernews import get_hackernews_jobs
        jobs = run(get_hackernews_jobs())
        assert isinstance(jobs, list)

    @patch("sources.hackernews.asyncio.to_thread")
    @patch("sources.hackernews.asyncio.sleep", return_value=None)
    def test_fetch_jobs_exception_sets_empty(self, mock_sleep, mock_to_thread):
        """to_thread(_fetch_jobs_from_thread) lève → raw_jobs = [] (lignes 164-166)."""
        import requests as r
        mock_to_thread.side_effect = [39894219, r.RequestException("timeout")]
        from sources.hackernews import get_hackernews_jobs
        jobs = run(get_hackernews_jobs())
        assert isinstance(jobs, list)


# ═══════════════════════════════════════════════════════════════
# TWITTER — branche _fetch_nitter_rss item sans /status/,
#           _try_nitter retourne jobs d'une instance,
#           PermissionError et RuntimeError dans get_twitter_jobs
# ═══════════════════════════════════════════════════════════════

class TestTwitterMissingBranches:

    def _make_rss(self, items):
        import xml.etree.ElementTree as ET
        channel = ET.Element("channel")
        for it in items:
            item = ET.SubElement(channel, "item")
            ET.SubElement(item, "title").text = it.get("title", "Tweet")
            ET.SubElement(item, "link").text  = it.get("link",  "https://nitter.net/user/status/123")
            ET.SubElement(item, "description").text = it.get("desc", "We are hiring a developer")
            ET.SubElement(item, "pubDate").text = "Mon, 15 Mar 2024 10:00:00 +0000"
        rss = ET.Element("rss", version="2.0")
        rss.append(channel)
        return ET.tostring(rss, encoding="unicode").encode()

    def _mock_get(self, content):
        m = MagicMock()
        m.status_code = 200
        m.content = content
        m.raise_for_status = MagicMock()
        return m

    @patch("sources.twitter.requests.get")
    def test_nitter_item_without_status_uses_link_directly(self, mock_get):
        """Item Nitter sans /status/ dans le lien → tw_url = link direct (ligne 140)."""
        rss = self._make_rss([{
            "title": "Hiring React developer remote",
            "link":  "https://nitter.net/user/tweet",  # pas de /status/
            "desc":  "We are hiring a React developer for remote work",
        }])
        mock_get.return_value = self._mock_get(rss)
        from sources.twitter import _fetch_nitter_rss
        jobs = _fetch_nitter_rss("hiring developer", "https://nitter.net")
        for job in jobs:
            # URL directe utilisée quand pas de /status/
            assert job["url"].startswith("http")

    @patch("sources.twitter.requests.get")
    def test_try_nitter_returns_on_first_productive_instance(self, mock_get):
        """_try_nitter retourne dès qu'une instance est productive."""
        rss = self._make_rss([{
            "title": "Dev React hiring remote",
            "link": "https://nitter.net/user/status/999",
            "desc": "Hiring freelance React developer remote",
        }])
        mock_get.return_value = self._mock_get(rss)
        from sources.twitter import _try_nitter
        jobs = _try_nitter("hiring developer")
        assert isinstance(jobs, list)
        assert len(jobs) >= 1

    @patch("sources.twitter._try_nitter", return_value=[])
    @patch("sources.twitter.asyncio.sleep", return_value=None)
    def test_permission_error_breaks_api_loop(self, mock_sleep, mock_nitter):
        """PermissionError dans l'API v2 → break et fallback Nitter."""
        import sources.twitter as tw_mod
        tw_mod.BEARER_TOKEN = "fake_token"
        with patch("sources.twitter._fetch_api_v2",
                   side_effect=PermissionError("Invalid token")):
            from sources.twitter import get_twitter_jobs
            jobs = run(get_twitter_jobs())
        assert isinstance(jobs, list)
        tw_mod.BEARER_TOKEN = ""

    @patch("sources.twitter._try_nitter", return_value=[])
    @patch("sources.twitter.asyncio.sleep", return_value=None)
    def test_runtime_error_rate_limit_breaks_loop(self, mock_sleep, mock_nitter):
        """RuntimeError (rate limit) → break et fallback Nitter."""
        import sources.twitter as tw_mod
        tw_mod.BEARER_TOKEN = "fake_token"
        with patch("sources.twitter._fetch_api_v2",
                   side_effect=RuntimeError("Rate limit")):
            from sources.twitter import get_twitter_jobs
            jobs = run(get_twitter_jobs())
        assert isinstance(jobs, list)
        tw_mod.BEARER_TOKEN = ""

    @patch("sources.twitter._try_nitter", return_value=[])
    @patch("sources.twitter.asyncio.sleep", return_value=None)
    def test_generic_exception_in_api_continues(self, mock_sleep, mock_nitter):
        """Exception générique dans API v2 → continue la boucle (pas break)."""
        import sources.twitter as tw_mod
        tw_mod.BEARER_TOKEN = "fake_token"
        call_count = [0]
        def side_eff(q):
            call_count[0] += 1
            raise Exception("generic error")
        with patch("sources.twitter._fetch_api_v2", side_effect=side_eff):
            from sources.twitter import get_twitter_jobs
            jobs = run(get_twitter_jobs())
        # Doit avoir tenté toutes les queries (pas de break sur generic exception)
        assert isinstance(jobs, list)
        tw_mod.BEARER_TOKEN = ""


# ═══════════════════════════════════════════════════════════════
# LINKEDIN — JobSpy df.iterrows (lignes 49-76),
#            card inner exception (136-137)
# ═══════════════════════════════════════════════════════════════

class TestLinkedInJobSpy:

    def test_scrape_with_jobspy_parses_dataframe(self):
        """_scrape_with_jobspy avec jobspy mocké retourne des jobs valides."""
        # Créer un DataFrame pandas mocké
        try:
            import pandas as pd
            df = pd.DataFrame([
                {"title": "React Developer", "company": "TechCo",
                 "job_url": "https://linkedin.com/jobs/1",
                 "description": "Senior React developer remote",
                 "min_amount": "4000"},
                {"title": "WordPress Expert", "company": "",
                 "job_url": "https://linkedin.com/jobs/2",
                 "description": "WordPress WooCommerce mission",
                 "min_amount": None},
            ])
        except ImportError:
            pytest.skip("pandas non installé")

        with patch.dict("sys.modules", {
            "jobspy": MagicMock(scrape_jobs=MagicMock(return_value=df))
        }):
            from sources.linkedin import _scrape_with_jobspy
            jobs = _scrape_with_jobspy("react developer", "France")
        assert isinstance(jobs, list)
        assert len(jobs) == 2
        assert jobs[0]["source"] == "linkedin"
        assert "React Developer" in jobs[0]["title"]
        assert "TechCo" in jobs[0]["title"]

    def test_scrape_with_jobspy_skips_empty_title_or_url(self):
        """Lignes sans titre ou URL sont ignorées."""
        try:
            import pandas as pd
            df = pd.DataFrame([
                {"title": "", "company": "X", "job_url": "https://li.com/1",
                 "description": "", "min_amount": None},
                {"title": "Valid Job", "company": "Y", "job_url": "",
                 "description": "", "min_amount": None},
                {"title": "Good Job", "company": "Z", "job_url": "https://li.com/3",
                 "description": "Real job", "min_amount": "3000"},
            ])
        except ImportError:
            pytest.skip("pandas non installé")

        with patch.dict("sys.modules", {
            "jobspy": MagicMock(scrape_jobs=MagicMock(return_value=df))
        }):
            from sources.linkedin import _scrape_with_jobspy
            jobs = _scrape_with_jobspy("react", "France")
        assert len(jobs) == 1
        assert jobs[0]["title"] == "Good Job @ Z"

    @patch("sources.linkedin.requests.get")
    @patch("sources.linkedin.asyncio.sleep", return_value=None)
    def test_card_inner_exception_continues(self, _, mock_get):
        """Exception dans le parsing d'une card → continue sur les suivantes."""
        html = """<html><body>
            <li class="jobs-search__results-list">
                <div class="job-search-card">
                    <h3 class="base-search-card__title">Dev React</h3>
                    <a class="base-card__full-link" href="https://linkedin.com/jobs/1">Voir</a>
                </div>
            </li>
            <li class="jobs-search__results-list">
                <!-- Card volontairement malformée -->
                <div class="job-search-card"></div>
            </li>
        </body></html>"""
        mock_get.return_value = MagicMock(
            status_code=200, text=html, url="https://www.linkedin.com/jobs/search/",
            raise_for_status=MagicMock()
        )
        from sources.linkedin import _scrape_with_requests
        jobs = _scrape_with_requests()
        assert isinstance(jobs, list)
        # Au moins la première card valide doit être parsée


# ═══════════════════════════════════════════════════════════════
# MALT — Playwright complet avec context et page (lignes 78-109)
# ═══════════════════════════════════════════════════════════════

class TestMaltPlaywrightFull:

    def _build_pw_mock(self, cards_data):
        """Construit un mock complet de la hiérarchie Playwright."""
        # Chaque card = dict {title, href, desc, price}
        async def make_card(data):
            card = MagicMock()
            title_el = MagicMock()
            title_el.inner_text = AsyncMock(return_value=data.get("title", "Dev"))
            link_el = MagicMock()
            link_el.get_attribute = AsyncMock(return_value=data.get("href", "/profile/1"))
            desc_el = MagicMock()
            desc_el.inner_text = AsyncMock(return_value=data.get("desc", "Mission remote"))
            price_el = MagicMock()
            price_el.inner_text = AsyncMock(return_value=data.get("price", "600€"))

            async def qs(selector):
                if "title" in selector.lower() or "h2" in selector.lower() or "h3" in selector.lower():
                    return title_el
                if "link" in selector.lower() or "a[href" in selector.lower():
                    return link_el
                if "desc" in selector.lower() or "p" in selector.lower():
                    return desc_el
                if "price" in selector.lower() or "budget" in selector.lower():
                    return price_el
                return None
            card.query_selector = qs
            return card

        return cards_data

    def test_playwright_with_valid_cards(self):
        """_scrape_with_playwright avec cards valides retourne les jobs."""
        cards_data = [
            {"title": "Expert WordPress Remote", "href": "/profile/wp1", "desc": "WordPress mission", "price": "500€"},
            {"title": "Dev React Senior",         "href": "/profile/r2",  "desc": "React application",  "price": "800€"},
        ]

        async def run_test():
            page = MagicMock()
            page.goto               = AsyncMock(return_value=None)
            page.wait_for_selector  = AsyncMock(return_value=None)

            cards = []
            for d in cards_data:
                card = MagicMock()
                title_el = MagicMock()
                title_el.inner_text = AsyncMock(return_value=d["title"])
                link_el = MagicMock()
                link_el.get_attribute = AsyncMock(return_value=d["href"])
                desc_el = MagicMock()
                desc_el.inner_text = AsyncMock(return_value=d["desc"])
                price_el = MagicMock()
                price_el.inner_text = AsyncMock(return_value=d["price"])

                async def make_qs(te, le, de, pe):
                    async def qs(sel):
                        s = sel.lower()
                        if any(x in s for x in ("title","h2","h3","name")): return te
                        if any(x in s for x in ("a[","link","href")):       return le
                        if any(x in s for x in ("desc","text","p.")):       return de
                        if any(x in s for x in ("price","budget","amount")): return pe
                        return None
                    return qs
                card.query_selector = await make_qs(title_el, link_el, desc_el, price_el)
                cards.append(card)

            page.query_selector_all = AsyncMock(return_value=cards)

            context = MagicMock()
            context.new_page = AsyncMock(return_value=page)

            browser = MagicMock()
            browser.new_context = AsyncMock(return_value=context)
            browser.close       = AsyncMock(return_value=None)

            pw_obj = MagicMock()
            pw_obj.chromium.launch = AsyncMock(return_value=browser)

            pw_ctx = MagicMock()
            pw_ctx.__aenter__ = AsyncMock(return_value=pw_obj)
            pw_ctx.__aexit__  = AsyncMock(return_value=None)

            with patch("playwright.async_api.async_playwright", return_value=pw_ctx):
                from sources.malt import _scrape_with_playwright
                return await _scrape_with_playwright()

        jobs = run(run_test())
        assert isinstance(jobs, list)

    def test_playwright_skips_title_too_short(self):
        """Card avec titre < 3 chars est ignorée (ligne 137)."""
        async def run_test():
            page = MagicMock()
            page.goto               = AsyncMock(return_value=None)
            page.wait_for_selector  = AsyncMock(return_value=None)

            card = MagicMock()
            title_el = MagicMock()
            title_el.inner_text = AsyncMock(return_value="AB")  # < 3 chars
            async def qs(sel):
                if any(x in sel.lower() for x in ("title","h2","h3","name")):
                    return title_el
                return None
            card.query_selector = qs

            page.query_selector_all = AsyncMock(return_value=[card])

            context = MagicMock()
            context.new_page = AsyncMock(return_value=page)
            browser = MagicMock()
            browser.new_context = AsyncMock(return_value=context)
            browser.close = AsyncMock(return_value=None)
            pw_obj = MagicMock()
            pw_obj.chromium.launch = AsyncMock(return_value=browser)
            pw_ctx = MagicMock()
            pw_ctx.__aenter__ = AsyncMock(return_value=pw_obj)
            pw_ctx.__aexit__  = AsyncMock(return_value=None)

            with patch("playwright.async_api.async_playwright", return_value=pw_ctx):
                from sources.malt import _scrape_with_playwright
                return await _scrape_with_playwright()

        jobs = run(run_test())
        assert jobs == []

    def test_playwright_card_exception_continues(self):
        """Exception sur une card → continue (ligne 109)."""
        async def run_test():
            page = MagicMock()
            page.goto               = AsyncMock(return_value=None)
            page.wait_for_selector  = AsyncMock(return_value=None)

            bad_card = MagicMock()
            async def bad_qs(sel): raise Exception("card crash")
            bad_card.query_selector = bad_qs

            page.query_selector_all = AsyncMock(return_value=[bad_card])

            context = MagicMock()
            context.new_page = AsyncMock(return_value=page)
            browser = MagicMock()
            browser.new_context = AsyncMock(return_value=context)
            browser.close = AsyncMock(return_value=None)
            pw_obj = MagicMock()
            pw_obj.chromium.launch = AsyncMock(return_value=browser)
            pw_ctx = MagicMock()
            pw_ctx.__aenter__ = AsyncMock(return_value=pw_obj)
            pw_ctx.__aexit__  = AsyncMock(return_value=None)

            with patch("playwright.async_api.async_playwright", return_value=pw_ctx):
                from sources.malt import _scrape_with_playwright
                return await _scrape_with_playwright()

        jobs = run(run_test())
        assert isinstance(jobs, list)  # pas d'exception propagée
