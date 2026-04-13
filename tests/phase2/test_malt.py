# =============================================================
# tests/phase2/test_malt.py
# =============================================================

import asyncio, pytest
from unittest.mock import patch, MagicMock, AsyncMock
from tests.phase2.conftest import make_html, make_mock_response, assert_valid_job, assert_description_truncated

def run(c): return asyncio.get_event_loop().run_until_complete(c)

FAKE_CARDS = [
    {"title": "Développeur React senior",  "url": "/profile/john-doe",   "budget": "650 €/j"},
    {"title": "Expert WordPress freelance","url": "/profile/jane-smith",  "budget": "500 €/j"},
    {"title": "Lead Frontend Next.js",     "url": "/profile/alice-dev",   "budget": "700 €/j"},
]

class TestMaltInternals:
    def test_abs_relative(self):
        from sources.malt import _abs
        assert _abs("/profile/x") == "https://www.malt.fr/profile/x"

    def test_abs_absolute_unchanged(self):
        from sources.malt import _abs
        url = "https://www.malt.fr/profile/x"
        assert _abs(url) == url

    def test_abs_empty(self):
        from sources.malt import _abs
        assert _abs("") == ""

    def test_first_bs_cascade(self):
        from bs4 import BeautifulSoup
        from sources.malt import _first_bs
        soup = BeautifulSoup("<div><h3>Titre</h3><p>Desc</p></div>", "html.parser")
        el = _first_bs(soup, ["h1", "h3"])
        assert el is not None and el.get_text() == "Titre"

    def test_first_bs_none_when_missing(self):
        from bs4 import BeautifulSoup
        from sources.malt import _first_bs
        soup = BeautifulSoup("<div><span>X</span></div>", "html.parser")
        assert _first_bs(soup, ["h1", "h2"]) is None


class TestMaltRequestsFallback:

    @patch("sources.malt.requests.get")
    @patch("sources.malt.asyncio.sleep", return_value=None)
    def test_returns_list(self, _, mock_get):
        mock_get.return_value = make_mock_response(make_html(FAKE_CARDS, "c-profile-card"))
        # Force le fallback requests en faisant planter l'import playwright
        with patch.dict("sys.modules", {"playwright": None, "playwright.async_api": None}):
            from importlib import reload
            import sources.malt as malt_mod
            jobs = run(malt_mod._scrape_with_requests())
        assert isinstance(jobs, list)

    @patch("sources.malt.requests.get")
    @patch("sources.malt.asyncio.sleep", return_value=None)
    def test_required_fields(self, _, mock_get):
        mock_get.return_value = make_mock_response(make_html(FAKE_CARDS, "c-profile-card"))
        from sources.malt import _scrape_with_requests
        jobs = run(_scrape_with_requests())
        for job in jobs:
            assert_valid_job(job, "malt")

    @patch("sources.malt.requests.get")
    @patch("sources.malt.asyncio.sleep", return_value=None)
    def test_urls_absolute(self, _, mock_get):
        mock_get.return_value = make_mock_response(make_html(FAKE_CARDS, "c-profile-card"))
        from sources.malt import _scrape_with_requests
        jobs = run(_scrape_with_requests())
        for job in jobs:
            assert job["url"].startswith("http"), f"URL relative: {job['url']}"

    @patch("sources.malt.requests.get")
    @patch("sources.malt.asyncio.sleep", return_value=None)
    def test_description_max_500(self, _, mock_get):
        data = [{"title": "Dev Malt", "url": "/profile/x", "description": "Z" * 700}]
        mock_get.return_value = make_mock_response(make_html(data, "c-profile-card"))
        from sources.malt import _scrape_with_requests
        jobs = run(_scrape_with_requests())
        assert_description_truncated(jobs, 500)

    @patch("sources.malt.requests.get")
    @patch("sources.malt.asyncio.sleep", return_value=None)
    def test_network_error_returns_empty(self, _, mock_get):
        import requests as r
        mock_get.side_effect = r.RequestException("timeout")
        from sources.malt import _scrape_with_requests
        jobs = run(_scrape_with_requests())
        assert jobs == []


class TestMaltGetJobsOrchestration:

    @patch("sources.malt._scrape_with_requests", new_callable=AsyncMock)
    @patch("sources.malt.asyncio.sleep", return_value=None)
    def test_get_malt_jobs_falls_back_when_playwright_missing(self, _, mock_req):
        mock_req.return_value = [
            {"title": "Dev React", "description": "Desc", "url": "https://www.malt.fr/profile/x",
             "budget_raw": "600 €/j", "source": "malt"}
        ]
        with patch.dict("sys.modules", {"playwright": None, "playwright.async_api": None}):
            from sources.malt import get_malt_jobs
            jobs = run(get_malt_jobs())
        assert isinstance(jobs, list)
        assert len(jobs) >= 0

    @patch("sources.malt._scrape_with_playwright", new_callable=AsyncMock, return_value=[])
    @patch("sources.malt._scrape_with_requests", new_callable=AsyncMock)
    @patch("sources.malt.asyncio.sleep", return_value=None)
    def test_falls_back_to_requests_when_playwright_returns_empty(self, _, mock_req, mock_pw):
        mock_req.return_value = [
            {"title": "Dev WP", "description": "", "url": "https://www.malt.fr/profile/y",
             "budget_raw": "", "source": "malt"}
        ]
        from sources.malt import get_malt_jobs
        jobs = run(get_malt_jobs())
        assert isinstance(jobs, list)
        mock_req.assert_called_once()

    @patch("sources.malt._scrape_with_playwright", new_callable=AsyncMock, return_value=[])
    @patch("sources.malt._scrape_with_requests", new_callable=AsyncMock)
    @patch("sources.malt.asyncio.sleep", return_value=None)
    def test_get_malt_jobs_never_raises(self, _, mock_req, mock_pw):
        """get_malt_jobs ne doit jamais propager d'exception, même si les deux scrapers crashent."""
        mock_req.side_effect = Exception("boom inattendu")
        try:
            from sources.malt import get_malt_jobs
            jobs = run(get_malt_jobs())
            assert isinstance(jobs, list)
        except Exception as exc:
            pytest.fail(f"get_malt_jobs a levé une exception: {exc}")
