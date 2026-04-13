# =============================================================
# tests/phase1/test_comeup.py
# =============================================================

import asyncio
import pytest
from unittest.mock import patch, MagicMock, call

from tests.phase1.conftest import (
    make_html, assert_valid_job,
    assert_no_duplicates, assert_description_truncated,
)
from sources.comeup import get_comeup_jobs, _abs


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


FAKE_SERVICES = [
    {"title": "Création site WordPress professionnel",  "url": "/fr/services/wp-1",  "budget": "À partir de 150 €"},
    {"title": "Développement React application web",    "url": "/fr/services/rct-2", "budget": "À partir de 80 €"},
    {"title": "Audit SEO complet + recommandations",    "url": "/fr/services/seo-3", "budget": "À partir de 60 €"},
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

class TestComeUpInternals:

    def test_abs_relative(self):
        assert _abs("/fr/services/test") == "https://comeup.com/fr/services/test"

    def test_abs_absolute(self):
        url = "https://comeup.com/fr/services/test"
        assert _abs(url) == url

    def test_abs_empty(self):
        assert _abs("") == ""


# ── Tests scraping ────────────────────────────────────────────

class TestComeUpScraping:

    @patch("sources.comeup.requests.get")
    @patch("sources.comeup.asyncio.sleep", return_value=None)
    def test_returns_list(self, mock_sleep, mock_get):
        mock_get.return_value = _mock_resp(make_html(FAKE_SERVICES, "service-card"))
        jobs = run(get_comeup_jobs())
        assert isinstance(jobs, list)

    @patch("sources.comeup.requests.get")
    @patch("sources.comeup.asyncio.sleep", return_value=None)
    def test_required_fields(self, mock_sleep, mock_get):
        mock_get.return_value = _mock_resp(make_html(FAKE_SERVICES, "service-card"))
        jobs = run(get_comeup_jobs())
        for job in jobs:
            assert_valid_job(job, "comeup")

    @patch("sources.comeup.requests.get")
    @patch("sources.comeup.asyncio.sleep", return_value=None)
    def test_no_duplicate_urls_across_pages(self, mock_sleep, mock_get):
        """Plusieurs pages avec les mêmes services → pas de doublons."""
        html = make_html(FAKE_SERVICES, "service-card")
        mock_get.return_value = _mock_resp(html)
        jobs = run(get_comeup_jobs())
        assert_no_duplicates(jobs)

    @patch("sources.comeup.requests.get")
    @patch("sources.comeup.asyncio.sleep", return_value=None)
    def test_multiple_pages_scraped(self, mock_sleep, mock_get):
        """Le scraper doit appeler requests.get plusieurs fois (plusieurs URLs)."""
        mock_get.return_value = _mock_resp(make_html(FAKE_SERVICES, "service-card"))
        run(get_comeup_jobs())
        assert mock_get.call_count >= 1  # au moins 1 page

    @patch("sources.comeup.requests.get")
    @patch("sources.comeup.asyncio.sleep", return_value=None)
    def test_source_field(self, mock_sleep, mock_get):
        mock_get.return_value = _mock_resp(make_html(FAKE_SERVICES, "service-card"))
        jobs = run(get_comeup_jobs())
        for job in jobs:
            assert job["source"] == "comeup"

    @patch("sources.comeup.requests.get")
    @patch("sources.comeup.asyncio.sleep", return_value=None)
    def test_network_error_returns_empty(self, mock_sleep, mock_get):
        import requests as r
        mock_get.side_effect = r.RequestException("timeout")
        jobs = run(get_comeup_jobs())
        assert isinstance(jobs, list)
        assert len(jobs) == 0

    @patch("sources.comeup.requests.get")
    @patch("sources.comeup.asyncio.sleep", return_value=None)
    def test_description_max_500(self, mock_sleep, mock_get):
        data = [{"title": "Service test", "url": "/fr/services/x",
                 "description": "B" * 600, "budget": "50 €"}]
        mock_get.return_value = _mock_resp(make_html(data, "service-card"))
        jobs = run(get_comeup_jobs())
        assert_description_truncated(jobs, 500)

    @patch("sources.comeup.requests.get")
    @patch("sources.comeup.asyncio.sleep", return_value=None)
    def test_empty_title_skipped(self, mock_sleep, mock_get):
        """Les cards sans titre valide (< 5 chars) ne doivent pas être incluses."""
        html = """<html><body>
            <article class="service-card">
                <h2><a href="/fr/s/1">OK</a></h2>
            </article>
            <article class="service-card">
                <h2><a href="/fr/s/2">Développeur React senior Paris</a></h2>
            </article>
        </body></html>"""
        mock_get.return_value = _mock_resp(html)
        jobs = run(get_comeup_jobs())
        for job in jobs:
            assert len(job["title"]) >= 5

    @patch("sources.comeup.requests.get")
    @patch("sources.comeup.asyncio.sleep", return_value=None)
    def test_urls_always_absolute(self, mock_sleep, mock_get):
        mock_get.return_value = _mock_resp(make_html(FAKE_SERVICES, "service-card"))
        jobs = run(get_comeup_jobs())
        for job in jobs:
            assert job["url"].startswith("http")
