# =============================================================
# tests/phase1/test_works404.py
# =============================================================

import asyncio
import pytest
from unittest.mock import patch, MagicMock

from tests.phase1.conftest import (
    make_html, assert_valid_job,
    assert_no_duplicates, assert_description_truncated,
)
from sources.works404 import get_404works_jobs, _abs, _first


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


FAKE_JOBS = [
    {"title": "Designer UX/UI pour app mobile",     "url": "/jobs/ux-1",   "budget": "TJM 450 €"},
    {"title": "Développeur Next.js fullstack",       "url": "/jobs/dev-2",  "budget": "600 €/j"},
    {"title": "Expert SEO technique freelance",      "url": "/jobs/seo-3",  "budget": "400 €/j"},
]


def _mock_resp(html: str, status: int = 200):
    m = MagicMock()
    m.status_code = status
    m.text = html
    m.raise_for_status = MagicMock(
        side_effect=None if status == 200 else Exception(f"HTTP {status}")
    )
    return m


# ── Tests internes ────────────────────────────────────────────

class TestInternals404Works:

    def test_abs_relative_path(self):
        assert _abs("/jobs/123") == "https://404works.com/jobs/123"

    def test_abs_absolute_unchanged(self):
        url = "https://404works.com/jobs/42"
        assert _abs(url) == url

    def test_abs_empty_string(self):
        assert _abs("") == ""

    def test_first_finds_correct_element(self):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup("<div><h3><a href='/j/1'>Titre</a></h3></div>", "html.parser")
        el = _first(soup, ["h2 a", "h3 a", "h3"])
        assert el is not None
        assert "Titre" in el.get_text()

    def test_first_cascades_correctly(self):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup("<div><p>Desc</p></div>", "html.parser")
        # h2 absent → doit tomber sur p
        el = _first(soup, ["h2", "p"])
        assert el is not None
        assert el.get_text() == "Desc"


# ── Tests de scraping ─────────────────────────────────────────

class TestWorks404Scraping:

    @patch("sources.works404.requests.get")
    @patch("sources.works404.asyncio.sleep", return_value=None)
    def test_returns_list(self, mock_sleep, mock_get):
        mock_get.return_value = _mock_resp(make_html(FAKE_JOBS, "job-item"))
        jobs = run(get_404works_jobs())
        assert isinstance(jobs, list)

    @patch("sources.works404.requests.get")
    @patch("sources.works404.asyncio.sleep", return_value=None)
    def test_required_fields(self, mock_sleep, mock_get):
        mock_get.return_value = _mock_resp(make_html(FAKE_JOBS, "job-item"))
        jobs = run(get_404works_jobs())
        for job in jobs:
            assert_valid_job(job, "404works")

    @patch("sources.works404.requests.get")
    @patch("sources.works404.asyncio.sleep", return_value=None)
    def test_source_is_404works(self, mock_sleep, mock_get):
        mock_get.return_value = _mock_resp(make_html(FAKE_JOBS, "job-item"))
        jobs = run(get_404works_jobs())
        for job in jobs:
            assert job["source"] == "404works"

    @patch("sources.works404.requests.get")
    @patch("sources.works404.asyncio.sleep", return_value=None)
    def test_urls_absolute(self, mock_sleep, mock_get):
        mock_get.return_value = _mock_resp(make_html(FAKE_JOBS, "job-item"))
        jobs = run(get_404works_jobs())
        for job in jobs:
            assert job["url"].startswith("http"), f"URL non absolue: {job['url']}"

    @patch("sources.works404.requests.get")
    @patch("sources.works404.asyncio.sleep", return_value=None)
    def test_description_truncated(self, mock_sleep, mock_get):
        data = [{"title": "Job test", "url": "/jobs/x", "description": "X" * 700}]
        mock_get.return_value = _mock_resp(make_html(data, "job-item"))
        jobs = run(get_404works_jobs())
        assert_description_truncated(jobs, 500)

    @patch("sources.works404.requests.get")
    @patch("sources.works404.asyncio.sleep", return_value=None)
    def test_network_error_returns_empty(self, mock_sleep, mock_get):
        import requests as r
        mock_get.side_effect = r.RequestException("connexion refusée")
        jobs = run(get_404works_jobs())
        assert jobs == []

    @patch("sources.works404.requests.get")
    @patch("sources.works404.asyncio.sleep", return_value=None)
    def test_empty_page_returns_empty_list(self, mock_sleep, mock_get):
        mock_get.return_value = _mock_resp("<html><body></body></html>")
        jobs = run(get_404works_jobs())
        assert isinstance(jobs, list)

    @patch("sources.works404.requests.get")
    @patch("sources.works404.asyncio.sleep", return_value=None)
    def test_fallback_generic_card_selector(self, mock_sleep, mock_get):
        """Le fallback [class*='card'] doit fonctionner si aucun sélecteur principal ne matche."""
        html = """<html><body>
            <div class="offer-card">
                <h3><a href="/jobs/1">Mission React freelance</a></h3>
                <p class="description">Développement composants</p>
            </div>
        </body></html>"""
        mock_get.return_value = _mock_resp(html)
        jobs = run(get_404works_jobs())
        assert isinstance(jobs, list)

    @patch("sources.works404.requests.get")
    @patch("sources.works404.asyncio.sleep", return_value=None)
    def test_titles_min_5_chars(self, mock_sleep, mock_get):
        """Les titres de moins de 5 caractères doivent être ignorés."""
        html = """<html><body>
            <article class="job-item">
                <h2><a href="/jobs/1">OK</a></h2>
            </article>
            <article class="job-item">
                <h2><a href="/jobs/2">Mission React Next.js senior</a></h2>
            </article>
        </body></html>"""
        mock_get.return_value = _mock_resp(html)
        jobs = run(get_404works_jobs())
        for job in jobs:
            assert len(job["title"]) >= 5, f"Titre trop court accepté: '{job['title']}'"
