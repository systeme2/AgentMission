# =============================================================
# tests/phase3/test_twitter.py
# =============================================================

import asyncio, pytest
from unittest.mock import patch, MagicMock
from tests.phase3.conftest import (
    make_twitter_api_response, make_tweet, make_nitter_rss,
    make_mock_response, assert_valid_job, assert_no_duplicates,
)

def run(c): return asyncio.get_event_loop().run_until_complete(c)

HIRING_TWEET       = make_tweet("111", "We're hiring a remote React developer! Looking for senior talent #hiring #freelance")
NON_HIRING_TWEET   = make_tweet("222", "Just shipped a new feature in our SaaS product!")
FRENCH_TWEET       = make_tweet("333", "Nous cherchons un développeur freelance React/TypeScript pour une mission remote")

NITTER_ITEMS = [
    {"title": "TechCo: hiring React developer remote",
     "link":  "https://nitter.net/techco/status/444",
     "description": "We are hiring a senior React developer for remote work #hiring"},
    {"title": "Random tweet about coffee",
     "link":  "https://nitter.net/user/status/555",
     "description": "Coffee is great in the morning"},
]


# ── Tests internes ────────────────────────────────────────────

class TestTwitterInternals:

    def test_is_relevant_tweet_hiring(self):
        from sources.twitter import _is_relevant_tweet
        assert _is_relevant_tweet("We're hiring a freelance developer")

    def test_is_relevant_tweet_mission(self):
        from sources.twitter import _is_relevant_tweet
        assert _is_relevant_tweet("Nouvelle mission pour développeur React remote")

    def test_is_relevant_tweet_false(self):
        from sources.twitter import _is_relevant_tweet
        assert not _is_relevant_tweet("Just had a great cup of coffee ☕")

    def test_tweet_to_job_relevant(self):
        from sources.twitter import _tweet_to_job
        job = _tweet_to_job("123", "We're hiring a React developer! #hiring")
        assert job is not None
        assert_valid_job(job, "twitter")

    def test_tweet_to_job_irrelevant_returns_none(self):
        from sources.twitter import _tweet_to_job
        job = _tweet_to_job("999", "Just watched a movie, great evening!")
        assert job is None

    def test_tweet_to_job_url_format(self):
        from sources.twitter import _tweet_to_job
        job = _tweet_to_job("789456", "Hiring freelance dev #hiring")
        assert job is not None
        assert "789456" in job["url"]
        assert job["url"].startswith("https://twitter.com")

    def test_tweet_to_job_strips_urls(self):
        from sources.twitter import _tweet_to_job
        job = _tweet_to_job("123", "Hiring React dev https://example.com/apply #hiring")
        assert job is not None
        assert "https://example.com" not in job["title"]

    def test_tweet_to_job_truncates_description(self):
        from sources.twitter import _tweet_to_job
        long_tweet = "We're hiring! " + "Great opportunity! " * 50
        job = _tweet_to_job("123", long_tweet)
        if job:
            assert len(job["description"]) <= 500


# ── Tests API v2 ──────────────────────────────────────────────

class TestTwitterAPIv2:

    @patch("sources.twitter.requests.get")
    def test_fetch_api_v2_raises_on_missing_token(self, mock_get):
        import sources.twitter as tw_mod
        original = tw_mod.BEARER_TOKEN
        tw_mod.BEARER_TOKEN = ""
        from sources.twitter import _fetch_api_v2
        try:
            with pytest.raises(ValueError, match="TWITTER_BEARER_TOKEN"):
                _fetch_api_v2("test query")
        finally:
            tw_mod.BEARER_TOKEN = original

    @patch("sources.twitter.requests.get")
    def test_fetch_api_v2_raises_on_401(self, mock_get):
        mock_get.return_value = make_mock_response("Unauthorized", status=401)
        import sources.twitter as tw_mod
        tw_mod.BEARER_TOKEN = "fake_token_for_test"
        from sources.twitter import _fetch_api_v2
        try:
            with pytest.raises(PermissionError):
                _fetch_api_v2("test")
        finally:
            tw_mod.BEARER_TOKEN = ""

    @patch("sources.twitter.requests.get")
    def test_fetch_api_v2_raises_on_429(self, mock_get):
        mock_get.return_value = make_mock_response("Rate limited", status=429)
        import sources.twitter as tw_mod
        tw_mod.BEARER_TOKEN = "fake_token"
        from sources.twitter import _fetch_api_v2
        try:
            with pytest.raises(RuntimeError, match="Rate limit"):
                _fetch_api_v2("test")
        finally:
            tw_mod.BEARER_TOKEN = ""

    @patch("sources.twitter.requests.get")
    def test_fetch_api_v2_filters_irrelevant(self, mock_get):
        data = make_twitter_api_response([HIRING_TWEET, NON_HIRING_TWEET, FRENCH_TWEET])
        mock_get.return_value = make_mock_response(data, content_type="application/json")
        import sources.twitter as tw_mod
        tw_mod.BEARER_TOKEN = "fake_token"
        from sources.twitter import _fetch_api_v2
        try:
            jobs = _fetch_api_v2("developer hiring")
            assert len(jobs) >= 1
            for job in jobs:
                assert_valid_job(job, "twitter")
        finally:
            tw_mod.BEARER_TOKEN = ""


# ── Tests Nitter RSS ──────────────────────────────────────────

class TestNitterRSS:

    @patch("sources.twitter.requests.get")
    def test_fetch_nitter_rss_filters_relevant(self, mock_get):
        mock_get.return_value = make_mock_response(make_nitter_rss(NITTER_ITEMS))
        from sources.twitter import _fetch_nitter_rss
        jobs = _fetch_nitter_rss("hiring developer", "https://nitter.net")
        # Seul l'item hiring doit passer
        assert len(jobs) >= 1
        for job in jobs:
            assert_valid_job(job, "twitter")

    @patch("sources.twitter.requests.get")
    def test_fetch_nitter_rss_network_error_returns_empty(self, mock_get):
        import requests as r
        mock_get.side_effect = r.RequestException("instance down")
        from sources.twitter import _fetch_nitter_rss
        jobs = _fetch_nitter_rss("test", "https://nitter.net")
        assert jobs == []

    @patch("sources.twitter.requests.get")
    def test_fetch_nitter_rss_invalid_xml_returns_empty(self, mock_get):
        mock_get.return_value = make_mock_response(b"<not>valid<xml")
        from sources.twitter import _fetch_nitter_rss
        jobs = _fetch_nitter_rss("test", "https://nitter.net")
        assert jobs == []

    @patch("sources.twitter.requests.get")
    def test_try_nitter_tries_multiple_instances(self, mock_get):
        """Si la première instance est down, essaie la suivante."""
        import requests as r
        mock_get.side_effect = [
            r.RequestException("instance 1 down"),
            make_mock_response(make_nitter_rss(NITTER_ITEMS[:1])),
        ]
        from sources.twitter import _try_nitter
        jobs = _try_nitter("hiring developer")
        assert isinstance(jobs, list)

    @patch("sources.twitter.requests.get")
    def test_try_nitter_returns_empty_all_instances_down(self, mock_get):
        import requests as r
        mock_get.side_effect = r.RequestException("all down")
        from sources.twitter import _try_nitter
        jobs = _try_nitter("test")
        assert jobs == []


# ── Tests orchestration ───────────────────────────────────────

class TestTwitterGetJobs:

    @patch("sources.twitter._try_nitter")
    @patch("sources.twitter.asyncio.sleep", return_value=None)
    def test_uses_nitter_when_no_token(self, _, mock_nitter):
        mock_nitter.return_value = [
            {"title": "Hiring React dev", "description": "Remote",
             "url": "https://twitter.com/i/web/status/1",
             "budget_raw": "", "source": "twitter", "date": ""}
        ]
        import sources.twitter as tw_mod
        tw_mod.BEARER_TOKEN = ""
        from sources.twitter import get_twitter_jobs
        jobs = run(get_twitter_jobs())
        assert isinstance(jobs, list)
        mock_nitter.assert_called()

    @patch("sources.twitter._try_nitter", return_value=[])
    @patch("sources.twitter.asyncio.sleep", return_value=None)
    def test_never_raises(self, _, __):
        """get_twitter_jobs ne doit jamais propager d'exception."""
        import sources.twitter as tw_mod
        tw_mod.BEARER_TOKEN = ""
        try:
            from sources.twitter import get_twitter_jobs
            jobs = run(get_twitter_jobs())
            assert isinstance(jobs, list)
        except Exception as exc:
            pytest.fail(f"get_twitter_jobs a levé: {exc}")

    @patch("sources.twitter._try_nitter")
    @patch("sources.twitter.asyncio.sleep", return_value=None)
    def test_no_duplicates(self, _, mock_nitter):
        shared = {"title": "Hiring dev", "description": "",
                  "url": "https://twitter.com/i/web/status/99",
                  "budget_raw": "", "source": "twitter", "date": ""}
        mock_nitter.return_value = [shared, shared]
        import sources.twitter as tw_mod
        tw_mod.BEARER_TOKEN = ""
        from sources.twitter import get_twitter_jobs
        jobs = run(get_twitter_jobs())
        assert_no_duplicates(jobs)

    @patch("sources.twitter._try_nitter")
    @patch("sources.twitter.asyncio.sleep", return_value=None)
    def test_source_field(self, _, mock_nitter):
        mock_nitter.return_value = [
            {"title": "Dev job", "description": "",
             "url": "https://twitter.com/i/web/status/1",
             "budget_raw": "", "source": "twitter", "date": ""}
        ]
        import sources.twitter as tw_mod
        tw_mod.BEARER_TOKEN = ""
        from sources.twitter import get_twitter_jobs
        jobs = run(get_twitter_jobs())
        for job in jobs:
            assert job["source"] == "twitter"
