# =============================================================
# tests/phase4/test_notifier.py
# =============================================================
#
# Tests complets du notifier Telegram :
#   - Construction des messages
#   - Succès / échec envoi
#   - send_summary
#   - test_telegram
#   - Gestion d'erreurs réseau
# =============================================================

import pytest, json
from unittest.mock import patch, MagicMock
from tests.phase4.conftest import make_analyzed_job


def _mock_telegram(ok=True, status=200):
    m = MagicMock()
    m.status_code = status
    m.raise_for_status = MagicMock()
    m.json.return_value = {"ok": ok, "result": {"message_id": 42} if ok else None,
                           "description": "" if ok else "Bad Request"}
    return m


# ── _build_message ────────────────────────────────────────────

class TestBuildMessage:

    def test_contains_score_percentage(self):
        from agents.notifier import _build_message
        job = make_analyzed_job(1, score=0.75)
        msg = _build_message(job)
        assert "75%" in msg

    def test_contains_source(self):
        from agents.notifier import _build_message
        job = make_analyzed_job(1, "malt", 0.7)
        msg = _build_message(job)
        assert "malt" in msg.lower()

    def test_contains_url(self):
        from agents.notifier import _build_message
        job = make_analyzed_job(1, "codeur", 0.7)
        msg = _build_message(job)
        assert job["url"] in msg

    def test_contains_stack(self):
        from agents.notifier import _build_message
        job = make_analyzed_job(1, score=0.7)
        msg = _build_message(job)
        assert "wordpress" in msg.lower() or "react" in msg.lower()

    def test_contains_budget(self):
        from agents.notifier import _build_message
        job = make_analyzed_job(1, score=0.7)
        msg = _build_message(job)
        # Le budget estimé de l'analyse est 300€
        assert "300" in msg or "€" in msg or "non précisé" in msg.lower()

    def test_contains_remote_status(self):
        from agents.notifier import _build_message
        job = make_analyzed_job(1, score=0.7)
        msg = _build_message(job)
        assert "remote" in msg.lower() or "oui" in msg.lower() or "non" in msg.lower()

    def test_score_emoji_high(self):
        from agents.notifier import _score_emoji
        assert "🔥" in _score_emoji(0.85)

    def test_score_emoji_medium(self):
        from agents.notifier import _score_emoji
        assert "✅" in _score_emoji(0.50)

    def test_score_emoji_low(self):
        from agents.notifier import _score_emoji
        assert "📌" in _score_emoji(0.20)

    def test_source_emoji_codeur(self):
        from agents.notifier import _source_emoji
        assert _source_emoji("codeur") != ""

    def test_source_emoji_unknown(self):
        from agents.notifier import _source_emoji
        emoji = _source_emoji("unknown_source_xyz")
        assert isinstance(emoji, str) and len(emoji) > 0


# ── send_alert ────────────────────────────────────────────────

class TestSendAlert:

    @patch("agents.notifier.requests.post")
    def test_returns_true_on_success(self, mock_post):
        mock_post.return_value = _mock_telegram(ok=True)
        from agents.notifier import send_alert
        job = make_analyzed_job(1, score=0.8)
        assert send_alert(job) is True

    @patch("agents.notifier.requests.post")
    def test_returns_false_on_telegram_error(self, mock_post):
        mock_post.return_value = _mock_telegram(ok=False)
        from agents.notifier import send_alert
        job = make_analyzed_job(1, score=0.8)
        assert send_alert(job) is False

    @patch("agents.notifier.requests.post")
    def test_returns_false_on_network_error(self, mock_post):
        import requests as r
        mock_post.side_effect = r.RequestException("timeout")
        from agents.notifier import send_alert
        job = make_analyzed_job(1, score=0.8)
        assert send_alert(job) is False

    @patch("agents.notifier.requests.post")
    def test_sends_to_correct_endpoint(self, mock_post):
        mock_post.return_value = _mock_telegram(ok=True)
        from agents.notifier import send_alert
        from config.settings import settings
        job = make_analyzed_job(1, score=0.8)
        send_alert(job)
        call_url = mock_post.call_args[0][0]
        assert settings.TELEGRAM_TOKEN in call_url
        assert "sendMessage" in call_url

    @patch("agents.notifier.requests.post")
    def test_uses_markdown_parse_mode(self, mock_post):
        mock_post.return_value = _mock_telegram(ok=True)
        from agents.notifier import send_alert
        job = make_analyzed_job(1, score=0.8)
        send_alert(job)
        payload = mock_post.call_args[1].get("data") or mock_post.call_args[0][1]
        if isinstance(payload, dict):
            assert payload.get("parse_mode") == "Markdown"

    @patch("agents.notifier.requests.post")
    def test_never_raises(self, mock_post):
        mock_post.side_effect = Exception("unexpected crash")
        from agents.notifier import send_alert
        job = make_analyzed_job(1, score=0.8)
        try:
            result = send_alert(job)
            assert result is False
        except Exception as exc:
            pytest.fail(f"send_alert a levé: {exc}")


# ── send_summary ──────────────────────────────────────────────

class TestSendSummary:

    @patch("agents.notifier.requests.post")
    def test_sends_summary_message(self, mock_post):
        mock_post.return_value = _mock_telegram(ok=True)
        from agents.notifier import send_summary
        stats = {"total": 42, "sent": 15, "liked": 3,
                 "by_source": {"codeur": 20, "malt": 22}}
        send_summary(stats)
        assert mock_post.call_count == 1

    @patch("agents.notifier.requests.post")
    def test_summary_contains_stats(self, mock_post):
        mock_post.return_value = _mock_telegram(ok=True)
        from agents.notifier import send_summary
        stats = {"total": 99, "sent": 12, "liked": 5, "by_source": {}}
        send_summary(stats)
        text = mock_post.call_args[1].get("data", {}).get("text", "")
        if not text:
            text = str(mock_post.call_args)
        assert "99" in text or "12" in text

    @patch("agents.notifier.requests.post")
    def test_summary_never_raises_on_error(self, mock_post):
        import requests as r
        mock_post.side_effect = r.RequestException("timeout")
        from agents.notifier import send_summary
        try:
            send_summary({"total": 0, "sent": 0, "liked": 0, "by_source": {}})
        except Exception as exc:
            pytest.fail(f"send_summary a levé: {exc}")


# ── test_telegram ─────────────────────────────────────────────

class TestTestTelegram:

    @patch("agents.notifier.requests.post")
    def test_returns_true_when_ok(self, mock_post):
        mock_post.return_value = _mock_telegram(ok=True)
        from agents.notifier import test_telegram
        assert test_telegram() is True

    @patch("agents.notifier.requests.post")
    def test_returns_false_when_not_ok(self, mock_post):
        mock_post.return_value = _mock_telegram(ok=False)
        from agents.notifier import test_telegram
        assert test_telegram() is False

    @patch("agents.notifier.requests.post")
    def test_returns_false_on_exception(self, mock_post):
        mock_post.side_effect = Exception("crash")
        from agents.notifier import test_telegram
        assert test_telegram() is False
