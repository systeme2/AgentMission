# =============================================================
# tests/upgrades/test_upgrades.py
# =============================================================

import asyncio, pytest, json
from unittest.mock import patch, MagicMock, AsyncMock

def run(c): return asyncio.get_event_loop().run_until_complete(c)


# ═══════════════════════════════════════════════════════════════
# TELEGRAM BOT BIDIRECTIONNEL
# ═══════════════════════════════════════════════════════════════

class TestTelegramBotState:

    def setup_method(self):
        from core import telegram_bot as tb
        tb._agent_state["paused"]      = False
        tb._agent_state["pause_until"] = None

    def test_is_not_paused_by_default(self):
        from core.telegram_bot import is_paused
        assert is_paused() is False

    def test_pause_sets_paused(self):
        from core.telegram_bot import _agent_state, is_paused
        from core import telegram_bot as tb
        from datetime import datetime, timedelta
        tb._agent_state["paused"]      = True
        tb._agent_state["pause_until"] = datetime.now() + timedelta(minutes=30)
        assert is_paused() is True

    def test_pause_expires_automatically(self):
        from core import telegram_bot as tb
        from core.telegram_bot import is_paused
        from datetime import datetime, timedelta
        tb._agent_state["paused"]      = True
        tb._agent_state["pause_until"] = datetime.now() - timedelta(seconds=1)
        # La pause a expiré → doit retourner False
        assert is_paused() is False
        assert tb._agent_state["paused"] is False

    def test_get_state_returns_dict(self):
        from core.telegram_bot import get_state
        state = get_state()
        assert isinstance(state, dict)
        assert "paused" in state

    def test_resume_clears_pause(self):
        from core import telegram_bot as tb
        from core.telegram_bot import _handle_resume, is_paused
        from datetime import datetime, timedelta
        tb._agent_state["paused"]      = True
        tb._agent_state["pause_until"] = datetime.now() + timedelta(hours=1)
        with patch("core.telegram_bot._send"):
            _handle_resume("12345")
        assert is_paused() is False


class TestTelegramBotKeyboard:

    def test_make_job_keyboard_has_3_buttons(self):
        from core.telegram_bot import make_job_keyboard
        kb = make_job_keyboard("https://example.com/job/1")
        row = kb["inline_keyboard"][0]
        assert len(row) == 3

    def test_make_job_keyboard_callback_data(self):
        from core.telegram_bot import make_job_keyboard
        kb = make_job_keyboard("https://example.com/job/1")
        actions = {btn["callback_data"].split(":")[0] for btn in kb["inline_keyboard"][0]}
        assert "like" in actions
        assert "dislike" in actions
        assert "apply" in actions

    def test_register_and_retrieve_url(self):
        from core.telegram_bot import register_job_url, get_url_from_hash
        url = "https://codeur.com/missions/42"
        register_job_url(url)
        url_hash = str(abs(hash(url)))[:12]
        assert get_url_from_hash(url_hash) == url

    def test_unknown_hash_returns_none(self):
        from core.telegram_bot import get_url_from_hash
        assert get_url_from_hash("00000000") is None


class TestTelegramBotHandlers:

    def _call(self, handler, *args, mock_send=True):
        with patch("core.telegram_bot._send") as ms:
            handler(*args)
            return ms

    def test_handle_start_sends_message(self):
        from core.telegram_bot import _handle_start
        ms = self._call(_handle_start, "12345")
        ms.assert_called_once()
        text = ms.call_args[0][1]
        assert "/stats" in text

    def test_handle_stats_sends_message(self):
        from core.telegram_bot import _handle_stats
        with patch("core.telegram_bot.get_stats", return_value={
            "total": 42, "sent": 10, "liked": 3, "by_source": {"codeur": 20}
        }):
            ms = self._call(_handle_stats, "12345")
            ms.assert_called_once()
            text = ms.call_args[0][1]
            assert "42" in text

    def test_handle_pause_valid(self):
        from core import telegram_bot as tb
        from core.telegram_bot import _handle_pause
        with patch("core.telegram_bot._send"):
            _handle_pause("12345", 60)
        assert tb._agent_state["paused"] is True
        assert tb._agent_state["pause_until"] is not None
        tb._agent_state["paused"] = False

    def test_handle_pause_invalid_duration(self):
        from core.telegram_bot import _handle_pause
        ms = self._call(_handle_pause, "12345", 0)
        text = ms.call_args[0][1]
        assert "invalide" in text.lower() or "invalid" in text.lower()

    def test_handle_seuil_valid(self):
        from core.telegram_bot import _handle_seuil
        from config.settings import settings
        original = settings.MIN_SCORE
        with patch("core.telegram_bot._send"):
            _handle_seuil("12345", 0.6)
        assert settings.MIN_SCORE == 0.6
        settings.MIN_SCORE = original

    def test_handle_seuil_out_of_range(self):
        from core.telegram_bot import _handle_seuil
        ms = self._call(_handle_seuil, "12345", 0.0)
        text = ms.call_args[0][1]
        assert "invalide" in text.lower() or "invalid" in text.lower()

    def test_dispatch_unknown_command(self):
        from core.telegram_bot import _dispatch_update
        with patch("core.telegram_bot.settings") as mock_settings,              patch("core.telegram_bot._send") as ms:
            mock_settings.TELEGRAM_CHAT_ID = "12345"
            update = {"message": {"text": "/unknown", "chat": {"id": 12345}}}
            _dispatch_update(update)
            ms.assert_called_once()

    def test_dispatch_rejects_foreign_chat(self):
        from core.telegram_bot import _dispatch_update
        update = {"message": {"text": "/stats", "chat": {"id": 9999999}}}
        with patch("core.telegram_bot._send") as ms:
            _dispatch_update(update)
            text = ms.call_args[0][1]
            assert "refusé" in text.lower() or "access" in text.lower()

    def test_callback_like_updates_status(self):
        from core.telegram_bot import register_job_url, _handle_callback
        url = "https://example.com/job/like-test"
        register_job_url(url)
        url_hash = str(abs(hash(url)))[:12]
        callback = {
            "id":      "abc123",
            "data":    f"like:{url_hash}",
            "from":    {"first_name": "Test"},
            "message": {"message_id": 1, "chat": {"id": 12345}},
        }
        with patch("core.telegram_bot.update_status") as mu, \
             patch("core.telegram_bot.save_feedback") as mf, \
             patch("core.telegram_bot.record_like"), \
             patch("core.telegram_bot.get_all_missions", return_value=[]), \
             patch("core.telegram_bot._answer_callback"), \
             patch("core.telegram_bot._edit_message_feedback"):
            _handle_callback(callback)
            mu.assert_called_once_with(url, "liked")
            mf.assert_called_once()



# ═══════════════════════════════════════════════════════════════
# TELEGRAM BOT — COUVERTURE COMPLÈTE
# ═══════════════════════════════════════════════════════════════

class TestTelegramBotAPIHelpers:
    """Couvre _api, _send, _answer_callback, _edit_message."""

    @patch("core.telegram_bot.requests.post")
    def test_api_returns_json_on_success(self, mock_post):
        from core.telegram_bot import _api
        mock_post.return_value = MagicMock(json=lambda: {"ok": True})
        result = _api("sendMessage", {"text": "test"})
        assert result == {"ok": True}

    @patch("core.telegram_bot.requests.post", side_effect=Exception("timeout"))
    def test_api_returns_false_on_exception(self, mock_post):
        from core.telegram_bot import _api
        result = _api("sendMessage", {})
        assert result == {"ok": False}

    @patch("core.telegram_bot._api")
    def test_send_calls_api(self, mock_api):
        from core.telegram_bot import _send
        _send("12345", "hello")
        mock_api.assert_called_once()
        args = mock_api.call_args[0]
        assert args[0] == "sendMessage"
        assert args[1]["text"] == "hello"

    @patch("core.telegram_bot._api")
    def test_send_with_reply_markup(self, mock_api):
        from core.telegram_bot import _send
        kb = {"inline_keyboard": []}
        _send("12345", "hello", reply_markup=kb)
        payload = mock_api.call_args[0][1]
        assert "reply_markup" in payload

    @patch("core.telegram_bot._api")
    def test_answer_callback_calls_api(self, mock_api):
        from core.telegram_bot import _answer_callback
        _answer_callback("cb123", "OK")
        mock_api.assert_called_once()
        assert mock_api.call_args[0][1]["callback_query_id"] == "cb123"

    @patch("core.telegram_bot._api")
    def test_edit_message_calls_api(self, mock_api):
        from core.telegram_bot import _edit_message
        _edit_message("12345", 99, "new text")
        mock_api.assert_called_once()
        payload = mock_api.call_args[0][1]
        assert payload["message_id"] == 99
        assert payload["text"] == "new text"

    @patch("core.telegram_bot._api")
    def test_edit_message_feedback_all_actions(self, mock_api):
        from core.telegram_bot import _edit_message_feedback
        for action in ("liked", "disliked", "applied"):
            _edit_message_feedback("12345", 1, action)
        assert mock_api.call_count == 3


class TestTelegramBotTop5AndStatus:

    @patch("core.telegram_bot._send")
    @patch("core.telegram_bot.get_all_missions", return_value=[])
    def test_top5_empty(self, mock_missions, mock_send):
        from core.telegram_bot import _handle_top5
        _handle_top5("12345")
        text = mock_send.call_args[0][1]
        assert "aucune" in text.lower() or "attente" in text.lower()

    @patch("core.telegram_bot._send")
    @patch("core.telegram_bot.get_all_missions")
    def test_top5_with_missions(self, mock_missions, mock_send):
        from core.telegram_bot import _handle_top5
        mock_missions.return_value = [
            {"title": f"Mission {i}", "url": f"https://x.com/{i}",
             "source": "codeur", "score": 0.8 - i*0.1, "status": "sent"}
            for i in range(3)
        ]
        _handle_top5("12345")
        text = mock_send.call_args[0][1]
        assert "Top 5" in text or "Mission" in text

    @patch("core.telegram_bot._send")
    def test_status_active(self, mock_send):
        from core import telegram_bot as tb
        from core.telegram_bot import _handle_status
        tb._agent_state["paused"] = False
        _handle_status("12345")
        text = mock_send.call_args[0][1]
        assert "actif" in text.lower() or "active" in text.lower()

    @patch("core.telegram_bot._send")
    def test_status_paused(self, mock_send):
        from core import telegram_bot as tb
        from core.telegram_bot import _handle_status
        from datetime import datetime, timedelta
        tb._agent_state["paused"]      = True
        tb._agent_state["pause_until"] = datetime.now() + timedelta(hours=1)
        _handle_status("12345")
        text = mock_send.call_args[0][1]
        assert "pause" in text.lower()
        tb._agent_state["paused"] = False
        tb._agent_state["pause_until"] = None


class TestTelegramBotCallbacksAll:

    @patch("core.telegram_bot._answer_callback")
    @patch("core.telegram_bot._edit_message_feedback")
    @patch("core.telegram_bot.update_status")
    @patch("core.telegram_bot.save_feedback")
    @patch("core.telegram_bot.record_dislike")
    @patch("core.telegram_bot.get_all_missions", return_value=[{"url": "https://x.com/1", "title": "T"}])
    def test_callback_dislike(self, mock_missions, mock_dislike, mock_fb, mock_status, mock_edit, mock_ans):
        from core.telegram_bot import register_job_url, _handle_callback
        url = "https://example.com/dislike-test"
        register_job_url(url)
        url_hash = str(abs(hash(url)))[:12]
        cb = {"id": "x", "data": f"dislike:{url_hash}",
              "from": {"first_name": "T"},
              "message": {"message_id": 2, "chat": {"id": 12345}}}
        _handle_callback(cb)
        mock_status.assert_called_with(url, "disliked")

    @patch("core.telegram_bot._answer_callback")
    @patch("core.telegram_bot._edit_message_feedback")
    @patch("core.telegram_bot.update_status")
    @patch("core.telegram_bot.save_feedback")
    def test_callback_apply(self, mock_fb, mock_status, mock_edit, mock_ans):
        from core.telegram_bot import register_job_url, _handle_callback
        url = "https://example.com/apply-test"
        register_job_url(url)
        url_hash = str(abs(hash(url)))[:12]
        cb = {"id": "y", "data": f"apply:{url_hash}",
              "from": {"first_name": "T"},
              "message": {"message_id": 3, "chat": {"id": 12345}}}
        _handle_callback(cb)
        mock_status.assert_called_with(url, "applied")

    @patch("core.telegram_bot._send")
    def test_dispatch_callback_query(self, mock_send):
        from core.telegram_bot import _dispatch_update, _handle_callback
        update = {"callback_query": {"id": "z", "data": "noop:",
                  "from": {"first_name": "T"},
                  "message": {"message_id": 1, "chat": {"id": 12345}}}}
        with patch("core.telegram_bot._handle_callback") as mock_cb:
            _dispatch_update(update)
            mock_cb.assert_called_once()


class TestTelegramBotDispatchEdgeCases:

    def _dispatch(self, text, chat_id=None):
        from config.settings import settings
        from core.telegram_bot import _dispatch_update
        cid = chat_id or settings.TELEGRAM_CHAT_ID
        update = {"message": {"text": text, "chat": {"id": int(cid) if str(cid).isdigit() else 0}}}
        with patch("core.telegram_bot._send") as ms,              patch("core.telegram_bot._handle_pause") as mh,              patch("core.telegram_bot._handle_seuil") as ms2:
            _dispatch_update(update)
            return ms, mh, ms2

    @patch("core.telegram_bot._send")
    def test_pause_without_arg_shows_usage(self, mock_send):
        from core.telegram_bot import _dispatch_update
        from config.settings import settings
        update = {"message": {"text": "/pause", "chat": {"id": int(settings.TELEGRAM_CHAT_ID) if settings.TELEGRAM_CHAT_ID.isdigit() else 12345}}}
        with patch("core.telegram_bot.settings") as ms:
            ms.TELEGRAM_CHAT_ID = "12345"
            update["message"]["chat"]["id"] = 12345
            _dispatch_update(update)
            mock_send.assert_called()

    @patch("core.telegram_bot._send")
    def test_seuil_without_arg_shows_usage(self, mock_send):
        from core.telegram_bot import _dispatch_update
        from core import telegram_bot as tb
        old_id = tb.settings.TELEGRAM_CHAT_ID
        tb.settings.TELEGRAM_CHAT_ID = "12345"
        update = {"message": {"text": "/seuil", "chat": {"id": 12345}}}
        _dispatch_update(update)
        mock_send.assert_called()
        tb.settings.TELEGRAM_CHAT_ID = old_id

    @patch("core.telegram_bot._send")
    def test_empty_message_ignored(self, mock_send):
        from core.telegram_bot import _dispatch_update
        update = {"message": {"text": "", "chat": {"id": 12345}}}
        _dispatch_update(update)
        mock_send.assert_not_called()

    @patch("core.telegram_bot._send")
    def test_no_message_key_ignored(self, mock_send):
        from core.telegram_bot import _dispatch_update
        _dispatch_update({})
        mock_send.assert_not_called()


class TestTelegramBotPolling:
    """Couvre run_polling via simulation d'une itération."""

    @patch("core.telegram_bot.asyncio.sleep", return_value=None)
    @patch("core.telegram_bot.requests.get")
    @patch("core.telegram_bot._dispatch_update")
    def test_polling_dispatches_updates(self, mock_dispatch, mock_get, mock_sleep):
        import asyncio as aio
        from core.telegram_bot import run_polling

        call_count = 0
        def side_effect(*a, **kw):
            nonlocal call_count
            call_count += 1
            m = MagicMock()
            if call_count == 1:
                m.json.return_value = {"ok": True, "result": [
                    {"update_id": 1, "message": {"text": "/stats", "chat": {"id": 12345}}}
                ]}
            else:
                raise KeyboardInterrupt("stop")
            return m
        mock_get.side_effect = side_effect

        try:
            aio.get_event_loop().run_until_complete(run_polling())
        except (KeyboardInterrupt, Exception):
            pass
        assert mock_dispatch.call_count >= 1

    @patch("core.telegram_bot.asyncio.sleep", return_value=None)
    @patch("core.telegram_bot.requests.get")
    def test_polling_handles_not_ok_response(self, mock_get, mock_sleep):
        import asyncio as aio
        from core.telegram_bot import run_polling

        call_count = 0
        def side_effect(*a, **kw):
            nonlocal call_count
            call_count += 1
            m = MagicMock()
            if call_count == 1:
                m.json.return_value = {"ok": False}
            else:
                raise KeyboardInterrupt()
            return m
        mock_get.side_effect = side_effect

        try:
            aio.get_event_loop().run_until_complete(run_polling())
        except (KeyboardInterrupt, Exception):
            pass
        assert call_count >= 1

    @patch("core.telegram_bot.asyncio.sleep", return_value=None)
    @patch("core.telegram_bot.requests.get", side_effect=Exception("network"))
    def test_polling_handles_network_exception(self, mock_get, mock_sleep):
        import asyncio as aio
        from core.telegram_bot import run_polling

        call_count_sleep = [0]
        original_sleep = mock_sleep.side_effect

        async def stop_after_one(*a, **kw):
            call_count_sleep[0] += 1
            if call_count_sleep[0] >= 2:
                raise KeyboardInterrupt()

        mock_sleep.side_effect = stop_after_one

        try:
            aio.get_event_loop().run_until_complete(run_polling())
        except (KeyboardInterrupt, Exception):
            pass
        # Le polling a bien géré l'exception réseau
        assert call_count_sleep[0] >= 1


# ═══════════════════════════════════════════════════════════════
# SCORING SÉMANTIQUE
# ═══════════════════════════════════════════════════════════════

class TestSemanticScorer:

    def setup_method(self):
        from agents.semantic_scorer import clear_cache
        clear_cache()

    def test_returns_zero_without_api_key(self):
        from agents.semantic_scorer import semantic_score_bonus
        from config.settings import settings
        original = settings.OPENAI_API_KEY
        settings.OPENAI_API_KEY = "sk-..."
        try:
            bonus = run(semantic_score_bonus({"title": "Dev React", "description": ""}))
            assert bonus == 0.0
        finally:
            settings.OPENAI_API_KEY = original

    def test_cosine_similarity_identical_vectors(self):
        from agents.semantic_scorer import _cosine_similarity
        v = [1.0, 0.5, 0.3]
        assert abs(_cosine_similarity(v, v) - 1.0) < 0.001

    def test_cosine_similarity_orthogonal_vectors(self):
        from agents.semantic_scorer import _cosine_similarity
        assert abs(_cosine_similarity([1, 0, 0], [0, 1, 0])) < 0.001

    def test_cosine_similarity_zero_vector(self):
        from agents.semantic_scorer import _cosine_similarity
        assert _cosine_similarity([0, 0, 0], [1, 2, 3]) == 0.0

    def test_cosine_similarity_negative_values(self):
        from agents.semantic_scorer import _cosine_similarity
        result = _cosine_similarity([1, -1, 0], [1, 1, 0])
        assert -1.0 <= result <= 1.0

    @patch("agents.semantic_scorer._get_embedding_sync")
    def test_bonus_computed_with_mock_embeddings(self, mock_emb):
        """Avec de vrais embeddings mockés, le bonus doit être dans [0, 0.20]."""
        from agents.semantic_scorer import semantic_score_bonus
        from config.settings import settings
        original = settings.OPENAI_API_KEY
        settings.OPENAI_API_KEY = "sk-real-mock"
        try:
            # Vecteurs similaires → bonus élevé
            mock_emb.return_value = [1.0] * 100
            job = {"title": "React Developer", "description": "SPA react typescript",
                   "analysis": {"stack": ["react"]}}
            bonus = run(semantic_score_bonus(job))
            assert 0.0 <= bonus <= 0.20
        finally:
            settings.OPENAI_API_KEY = original

    @patch("agents.semantic_scorer._get_embedding_sync")
    def test_cache_avoids_duplicate_calls(self, mock_emb):
        """Le même texte ne doit être embedé qu'une seule fois."""
        from agents.semantic_scorer import _get_embedding, clear_cache
        from config.settings import settings
        clear_cache()
        original = settings.OPENAI_API_KEY
        settings.OPENAI_API_KEY = "sk-mock"
        mock_emb.return_value = [0.5] * 10
        try:
            run(_get_embedding("test text identical"))
            run(_get_embedding("test text identical"))  # doit utiliser le cache
            assert mock_emb.call_count == 1
        finally:
            settings.OPENAI_API_KEY = original

    @patch("agents.semantic_scorer._get_embedding_sync", return_value=None)
    def test_returns_zero_when_embedding_fails(self, mock_emb):
        from agents.semantic_scorer import semantic_score_bonus
        from config.settings import settings
        original = settings.OPENAI_API_KEY
        settings.OPENAI_API_KEY = "sk-mock"
        try:
            bonus = run(semantic_score_bonus({"title": "Dev", "description": ""}))
            assert bonus == 0.0
        finally:
            settings.OPENAI_API_KEY = original

    def test_scorer_integrates_semantic_bonus(self):
        """Le scorer principal doit avoir un champ semantic_bonus dans score_detail."""
        from agents.scorer import score_job
        job = {"title": "Développeur React freelance", "description": "Mission remote",
               "source": "codeur", "url": "https://example.com/1",
               "budget_raw": "500€",
               "analysis": {"stack": ["react"], "budget_estime": 500,
                             "remote": True, "est_freelance": True, "langue": "fr"}}
        result = run(score_job(job))
        assert "score_detail" in result
        assert "semantic_bonus" in result["score_detail"]
        assert 0.0 <= result["score"] <= 1.0


# ═══════════════════════════════════════════════════════════════
# MULTI-PROFILS
# ═══════════════════════════════════════════════════════════════

class TestProfiles:

    def test_all_profiles_exist(self):
        from config.profiles import PROFILES
        for name in ["all", "wordpress", "react", "seo", "international"]:
            assert name in PROFILES, f"Profil '{name}' manquant"

    def test_get_profile_returns_profile(self):
        from config.profiles import get_profile
        p = get_profile("wordpress")
        assert p.name  == "wordpress"
        assert len(p.keywords) > 0

    def test_get_profile_fallback_to_all(self):
        from config.profiles import get_profile
        p = get_profile("profil_inexistant_xyz")
        assert p.name == "all"

    def test_list_profiles(self):
        from config.profiles import list_profiles
        profiles = list_profiles()
        assert isinstance(profiles, list)
        assert len(profiles) >= 5

    def test_each_profile_has_required_fields(self):
        from config.profiles import PROFILES
        for name, p in PROFILES.items():
            assert p.name,    f"[{name}] name vide"
            assert p.label,   f"[{name}] label vide"
            assert p.keywords, f"[{name}] keywords vide"
            assert 0 < p.min_score < 1, f"[{name}] min_score hors bornes"
            assert p.min_budget > 0, f"[{name}] min_budget <= 0"

    def test_wordpress_profile_has_wordpress_keyword(self):
        from config.profiles import get_profile
        p = get_profile("wordpress")
        assert any("wordpress" in kw.lower() for kw in p.keywords)

    def test_react_profile_has_react_keyword(self):
        from config.profiles import get_profile
        p = get_profile("react")
        assert any("react" in kw.lower() for kw in p.keywords)

    def test_international_profile_sources_override(self):
        from config.profiles import get_profile
        p = get_profile("international")
        assert p.sources_override is not None
        assert "upwork" in p.sources_override

    def test_international_profile_prefers_english(self):
        from config.profiles import get_profile
        p = get_profile("international")
        assert "en" in p.preferred_langs

    def test_profile_applied_in_pipeline(self):
        """Le profil wordpress doit modifier les settings pendant le pipeline."""
        from config.settings import settings
        from config.profiles import get_profile
        from core import orchestrator as orch

        p = get_profile("wordpress")
        captured = {}

        async def fake_collect():
            captured["keywords"] = settings.PREFERRED_KEYWORDS[:]
            captured["min_score"] = settings.MIN_SCORE
            return []

        import agents.collector as col_mod
        orig_map = col_mod.SOURCE_MAP.copy()
        orig_en  = settings.SOURCES_ENABLED[:]
        col_mod.SOURCE_MAP = {"wordpress_source": fake_collect}
        settings.SOURCES_ENABLED = ["wordpress_source"]
        try:
            run(orch.run_pipeline(profile_name="wordpress"))
        finally:
            col_mod.SOURCE_MAP       = orig_map
            settings.SOURCES_ENABLED = orig_en

        assert "wordpress" in [kw.lower() for kw in captured.get("keywords", [])]
        assert captured.get("min_score") == p.min_score

    def test_settings_restored_after_pipeline(self):
        """Les settings doivent être restaurés après le pipeline."""
        from config.settings import settings, Settings
        from core import orchestrator as orch
        import agents.collector as col_mod

        # Utiliser les valeurs d'une instance fraîche pour ne pas dépendre
        # de l'état muté par les tests précédents
        fresh        = Settings()
        settings.PREFERRED_KEYWORDS = fresh.PREFERRED_KEYWORDS[:]
        settings.MIN_SCORE          = fresh.MIN_SCORE

        original_kw    = settings.PREFERRED_KEYWORDS[:]
        original_score = settings.MIN_SCORE

        async def fake_collect(): return []
        orig_map = col_mod.SOURCE_MAP.copy()
        orig_en  = settings.SOURCES_ENABLED[:]
        col_mod.SOURCE_MAP       = {"s": fake_collect}
        settings.SOURCES_ENABLED = ["s"]
        try:
            run(orch.run_pipeline(profile_name="seo"))
        finally:
            col_mod.SOURCE_MAP       = orig_map
            settings.SOURCES_ENABLED = orig_en

        assert settings.PREFERRED_KEYWORDS == original_kw
        assert settings.MIN_SCORE          == original_score


# ═══════════════════════════════════════════════════════════════
# NOUVELLES SOURCES
# ═══════════════════════════════════════════════════════════════

class TestGitHubJobs:

    def _mock_resp(self, data, status=200):
        m = MagicMock()
        m.status_code = status
        m.json.return_value = data
        m.raise_for_status = MagicMock()
        return m

    def test_is_relevant_hiring_issue(self):
        from sources.github_jobs import _is_relevant_issue
        issue = {"title": "Hiring: Remote React Developer",
                 "body": "We are looking for a freelance developer"}
        assert _is_relevant_issue(issue)

    def test_is_relevant_excludes_bug_reports(self):
        from sources.github_jobs import _is_relevant_issue
        issue = {"title": "Bug: login fails on mobile", "body": "Steps to reproduce..."}
        assert not _is_relevant_issue(issue)

    def test_parse_issue_valid(self):
        from sources.github_jobs import _parse_issue
        issue = {"title": "Senior React Developer needed",
                 "html_url": "https://github.com/org/repo/issues/1",
                 "body": "We need a React developer for our startup."}
        job = _parse_issue(issue)
        assert job is not None
        assert job["source"] == "github.jobs"
        assert job["url"].startswith("http")

    def test_parse_issue_empty_title_returns_none(self):
        from sources.github_jobs import _parse_issue
        assert _parse_issue({"title": "", "html_url": "https://github.com/x"}) is None

    @patch("sources.github_jobs.requests.get")
    @patch("sources.github_jobs.asyncio.sleep", return_value=None)
    def test_returns_list(self, _, mock_get):
        mock_get.return_value = self._mock_resp({"items": [
            {"title": "Hiring React Developer", "html_url": "https://github.com/issues/1",
             "body": "Looking for a freelance React developer remote"}
        ]})
        from sources.github_jobs import get_github_jobs
        jobs = run(get_github_jobs())
        assert isinstance(jobs, list)

    @patch("sources.github_jobs.requests.get")
    @patch("sources.github_jobs.asyncio.sleep", return_value=None)
    def test_rate_limit_handled(self, _, mock_get):
        m = self._mock_resp({}, status=403)
        m.status_code = 403
        mock_get.return_value = m
        from sources.github_jobs import get_github_jobs
        jobs = run(get_github_jobs())
        assert isinstance(jobs, list)

    @patch("sources.github_jobs.requests.get")
    @patch("sources.github_jobs.asyncio.sleep", return_value=None)
    def test_network_error_returns_empty(self, _, mock_get):
        import requests as r
        mock_get.side_effect = r.RequestException("timeout")
        from sources.github_jobs import get_github_jobs
        jobs = run(get_github_jobs())
        assert isinstance(jobs, list)

    @patch("sources.github_jobs.requests.get")
    @patch("sources.github_jobs.asyncio.sleep", return_value=None)
    def test_no_duplicates(self, _, mock_get):
        same_item = {"title": "Hiring Dev", "html_url": "https://github.com/issues/1",
                     "body": "freelance remote developer"}
        mock_get.return_value = self._mock_resp({"items": [same_item, same_item]})
        from sources.github_jobs import get_github_jobs
        jobs = run(get_github_jobs())
        urls = [j["url"] for j in jobs]
        assert len(urls) == len(set(urls))


class TestRSSCustom:

    def _make_rss(self, items: list) -> bytes:
        import xml.etree.ElementTree as ET
        channel = ET.Element("channel")
        for it in items:
            item = ET.SubElement(channel, "item")
            ET.SubElement(item, "title").text       = it.get("title", "Job")
            ET.SubElement(item, "link").text         = it.get("link", "https://example.com/1")
            ET.SubElement(item, "description").text  = it.get("desc", "Description")
        rss = ET.Element("rss", version="2.0")
        rss.append(channel)
        return ET.tostring(rss, encoding="unicode").encode()

    def _mock_resp(self, content: bytes, status=200):
        m = MagicMock()
        m.status_code = status
        m.content = content
        m.raise_for_status = MagicMock()
        return m

    def test_returns_empty_without_feeds(self):
        from sources.rss_custom import get_custom_rss_jobs
        from config.settings import settings
        original = settings.CUSTOM_RSS_FEEDS
        settings.CUSTOM_RSS_FEEDS = []
        try:
            jobs = run(get_custom_rss_jobs())
            assert jobs == []
        finally:
            settings.CUSTOM_RSS_FEEDS = original

    @patch("sources.rss_custom.requests.get")
    @patch("sources.rss_custom.asyncio.sleep", return_value=None)
    def test_parses_rss_feed(self, _, mock_get):
        rss = self._make_rss([
            {"title": "Dev React freelance", "link": "https://example.com/job/1", "desc": "Mission React remote"}
        ])
        mock_get.return_value = self._mock_resp(rss)
        from sources.rss_custom import get_custom_rss_jobs
        from config.settings import settings
        original = settings.CUSTOM_RSS_FEEDS
        settings.CUSTOM_RSS_FEEDS = ["https://example.com/feed.rss"]
        try:
            jobs = run(get_custom_rss_jobs())
            assert isinstance(jobs, list)
            assert len(jobs) >= 1
            assert jobs[0]["source"].startswith("rss:")
        finally:
            settings.CUSTOM_RSS_FEEDS = original

    @patch("sources.rss_custom.requests.get")
    @patch("sources.rss_custom.asyncio.sleep", return_value=None)
    def test_handles_invalid_xml(self, _, mock_get):
        mock_get.return_value = self._mock_resp(b"<not>valid<xml>>>")
        from sources.rss_custom import get_custom_rss_jobs
        from config.settings import settings
        original = settings.CUSTOM_RSS_FEEDS
        settings.CUSTOM_RSS_FEEDS = ["https://example.com/bad.rss"]
        try:
            jobs = run(get_custom_rss_jobs())
            assert isinstance(jobs, list)
        finally:
            settings.CUSTOM_RSS_FEEDS = original

    @patch("sources.rss_custom.requests.get")
    @patch("sources.rss_custom.asyncio.sleep", return_value=None)
    def test_network_error_returns_empty(self, _, mock_get):
        import requests as r
        mock_get.side_effect = r.RequestException("timeout")
        from sources.rss_custom import get_custom_rss_jobs
        from config.settings import settings
        original = settings.CUSTOM_RSS_FEEDS
        settings.CUSTOM_RSS_FEEDS = ["https://example.com/feed.rss"]
        try:
            jobs = run(get_custom_rss_jobs())
            assert isinstance(jobs, list)
        finally:
            settings.CUSTOM_RSS_FEEDS = original

    @patch("sources.rss_custom.requests.get")
    @patch("sources.rss_custom.asyncio.sleep", return_value=None)
    def test_dedup_across_multiple_feeds(self, _, mock_get):
        rss = self._make_rss([
            {"title": "Dev Remote", "link": "https://example.com/job/99"}
        ])
        mock_get.return_value = self._mock_resp(rss)
        from sources.rss_custom import get_custom_rss_jobs
        from config.settings import settings
        original = settings.CUSTOM_RSS_FEEDS
        settings.CUSTOM_RSS_FEEDS = [
            "https://feed1.com/rss", "https://feed2.com/rss"
        ]
        try:
            jobs = run(get_custom_rss_jobs())
            urls = [j["url"] for j in jobs]
            assert len(urls) == len(set(urls))
        finally:
            settings.CUSTOM_RSS_FEEDS = original

    def test_required_fields_in_parsed_jobs(self):
        """Les jobs RSS doivent avoir tous les champs requis."""
        import xml.etree.ElementTree as ET
        from sources.rss_custom import _parse_rss2
        rss_xml = """<rss><channel>
            <item>
                <title>Dev React Paris</title>
                <link>https://example.com/job/1</link>
                <description>Mission React remote, budget 600€</description>
            </item>
        </channel></rss>"""
        root = ET.fromstring(rss_xml)
        jobs = _parse_rss2(root, "https://example.com/feed.rss")
        assert len(jobs) == 1
        for field in ("title", "description", "url", "budget_raw", "source"):
            assert field in jobs[0], f"Champ '{field}' manquant"


# ═══════════════════════════════════════════════════════════════
# INTÉGRATION — nouvelles sources dans SOURCE_MAP
# ═══════════════════════════════════════════════════════════════

class TestNewSourcesRegistration:

    def test_github_jobs_in_source_map(self):
        from agents.collector import SOURCE_MAP
        assert "github.jobs" in SOURCE_MAP

    def test_rss_custom_in_source_map(self):
        from agents.collector import SOURCE_MAP
        assert "rss.custom" in SOURCE_MAP

    def test_source_map_now_23_sources(self):
        from agents.collector import SOURCE_MAP
        assert len(SOURCE_MAP) == 23, f"Attendu 23, obtenu {len(SOURCE_MAP)}"

    def test_settings_has_new_keys(self):
        from config.settings import settings
        assert hasattr(settings, "ACTIVE_PROFILE")
        assert hasattr(settings, "TELEGRAM_BOT_ENABLED")
        assert hasattr(settings, "SEMANTIC_SCORING_ENABLED")
        assert hasattr(settings, "CUSTOM_RSS_FEEDS")
        assert hasattr(settings, "IDEAL_PROFILE_TEXT")
