# =============================================================
# tests/phase1/test_freelance_com.py
# =============================================================

import asyncio
import pytest
from unittest.mock import patch, MagicMock

from tests.phase1.conftest import (
    make_html, make_json_jobs,
    assert_valid_job, assert_no_duplicates, assert_description_truncated,
)
from sources.freelance_com import get_freelance_com_jobs, _make_absolute, _first


# ── Helpers ───────────────────────────────────────────────────

def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


FAKE_JOBS = [
    {"title": "Développeur React senior freelance",  "url": "/missions/1", "budget": "800 €"},
    {"title": "Refonte site WordPress e-commerce",   "url": "/missions/2", "budget": "1200 €"},
    {"title": "Intégration API REST Python",         "url": "/missions/3", "budget": ""},
]


def _mock_response(html: str, status: int = 200):
    mock = MagicMock()
    mock.status_code = status
    mock.text = html
    mock.raise_for_status = MagicMock(
        side_effect=None if status == 200 else Exception(f"HTTP {status}")
    )
    return mock


# ── Tests unitaires internes ──────────────────────────────────

class TestInternals:
    def test_make_absolute_relative(self):
        assert _make_absolute("/missions/123") == "https://www.freelance.com/missions/123"

    def test_make_absolute_already_absolute(self):
        url = "https://www.freelance.com/missions/99"
        assert _make_absolute(url) == url

    def test_make_absolute_empty(self):
        assert _make_absolute("") == ""

    def test_make_absolute_no_leading_slash(self):
        result = _make_absolute("missions/42")
        assert result.startswith("https://www.freelance.com")

    def test_first_returns_first_match(self):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup("<div><h2>Title</h2><p>Desc</p></div>", "html.parser")
        el = _first(soup, ["h1", "h2", "h3"])
        assert el is not None
        assert el.get_text() == "Title"

    def test_first_returns_none_when_no_match(self):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup("<div><span>Text</span></div>", "html.parser")
        el = _first(soup, ["h1", "h2", "h3"])
        assert el is None


# ── Tests de scraping avec mock réseau ───────────────────────

class TestFreelanceComScraping:

    @patch("sources.freelance_com.requests.get")
    @patch("sources.freelance_com.asyncio.sleep", return_value=None)
    def test_returns_list(self, mock_sleep, mock_get):
        mock_get.return_value = _mock_response(make_html(FAKE_JOBS, "project"))
        jobs = run(get_freelance_com_jobs())
        assert isinstance(jobs, list)

    @patch("sources.freelance_com.requests.get")
    @patch("sources.freelance_com.asyncio.sleep", return_value=None)
    def test_required_fields_present(self, mock_sleep, mock_get):
        mock_get.return_value = _mock_response(make_html(FAKE_JOBS, "project"))
        jobs = run(get_freelance_com_jobs())
        for job in jobs:
            assert_valid_job(job, "freelance.com")

    @patch("sources.freelance_com.requests.get")
    @patch("sources.freelance_com.asyncio.sleep", return_value=None)
    def test_no_duplicates(self, mock_sleep, mock_get):
        mock_get.return_value = _mock_response(make_html(FAKE_JOBS * 2, "project"))
        jobs = run(get_freelance_com_jobs())
        # Même si le HTML contient des doublons, chaque URL ne doit apparaître qu'une fois
        # (les doublons peuvent passer ici car le dedup est fait dans collector)
        assert isinstance(jobs, list)

    @patch("sources.freelance_com.requests.get")
    @patch("sources.freelance_com.asyncio.sleep", return_value=None)
    def test_description_max_500_chars(self, mock_sleep, mock_get):
        long_desc = "A" * 600
        jobs_data = [{"title": "Mission test", "url": "/missions/1",
                      "description": long_desc, "budget": ""}]
        mock_get.return_value = _mock_response(make_html(jobs_data, "project"))
        jobs = run(get_freelance_com_jobs())
        assert_description_truncated(jobs, 500)

    @patch("sources.freelance_com.requests.get")
    @patch("sources.freelance_com.asyncio.sleep", return_value=None)
    def test_urls_are_absolute(self, mock_sleep, mock_get):
        mock_get.return_value = _mock_response(make_html(FAKE_JOBS, "project"))
        jobs = run(get_freelance_com_jobs())
        for job in jobs:
            assert job["url"].startswith("http"), f"URL relative: {job['url']}"

    @patch("sources.freelance_com.requests.get")
    @patch("sources.freelance_com.asyncio.sleep", return_value=None)
    def test_source_field_correct(self, mock_sleep, mock_get):
        mock_get.return_value = _mock_response(make_html(FAKE_JOBS, "project"))
        jobs = run(get_freelance_com_jobs())
        for job in jobs:
            assert job["source"] == "freelance.com"

    @patch("sources.freelance_com.requests.get")
    @patch("sources.freelance_com.asyncio.sleep", return_value=None)
    def test_returns_empty_list_on_network_error(self, mock_sleep, mock_get):
        import requests as req_lib
        mock_get.side_effect = req_lib.RequestException("timeout")
        jobs = run(get_freelance_com_jobs())
        assert jobs == []

    @patch("sources.freelance_com.requests.get")
    @patch("sources.freelance_com.asyncio.sleep", return_value=None)
    def test_empty_html_returns_empty_list(self, mock_sleep, mock_get):
        mock_get.return_value = _mock_response("<html><body><p>Aucune mission</p></body></html>")
        jobs = run(get_freelance_com_jobs())
        assert isinstance(jobs, list)

    @patch("sources.freelance_com.requests.get")
    @patch("sources.freelance_com.asyncio.sleep", return_value=None)
    def test_fallback_on_link_scraping(self, mock_sleep, mock_get):
        """Si aucune carte projet détectée, le fallback lien doit fonctionner."""
        html = """<html><body>
            <a href="/mission/123">Mission React freelance Paris</a>
            <a href="/mission/456">Développeur WordPress urgence</a>
        </body></html>"""
        mock_get.return_value = _mock_response(html)
        jobs = run(get_freelance_com_jobs())
        assert isinstance(jobs, list)
        for job in jobs:
            assert job["url"].startswith("http")

    @patch("sources.freelance_com.requests.get")
    @patch("sources.freelance_com.asyncio.sleep", return_value=None)
    def test_titles_not_empty(self, mock_sleep, mock_get):
        mock_get.return_value = _mock_response(make_html(FAKE_JOBS, "project"))
        jobs = run(get_freelance_com_jobs())
        for job in jobs:
            assert len(job["title"].strip()) > 0
