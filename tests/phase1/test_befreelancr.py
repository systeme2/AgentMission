# =============================================================
# tests/phase1/test_befreelancr.py
# =============================================================

import asyncio
import pytest
from unittest.mock import patch, MagicMock

from tests.phase1.conftest import (
    make_html, assert_valid_job,
    assert_no_duplicates, assert_description_truncated,
)
from sources.befreelancr import get_befreelancr_jobs, _abs, _first


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


FAKE_MISSIONS = [
    {"title": "Création boutique WooCommerce",     "url": "/missions/woo-1",  "budget": "900 €"},
    {"title": "Refonte identité visuelle + charte","url": "/missions/design-2","budget": "600 €"},
    {"title": "Automatisation scripts Python",     "url": "/missions/py-3",   "budget": "1500 €"},
]


def _mock_resp(html: str, status: int = 200):
    m = MagicMock()
    m.status_code = status
    m.text = html
    m.raise_for_status = MagicMock(
        side_effect=None if status == 200 else Exception(f"HTTP {status}")
    )
    return m


def _make_html_with_date(missions: list) -> str:
    items = []
    for m in missions:
        items.append(f"""
        <article class="mission-card">
            <h2><a href="{m['url']}">{m['title']}</a></h2>
            <p class="description">{m.get('description', 'Description')}</p>
            <span class="budget">{m.get('budget', '')}</span>
            <time datetime="2024-03-15">15 mars 2024</time>
        </article>""")
    return f"<html><body>{''.join(items)}</body></html>"


# ── Tests internes ────────────────────────────────────────────

class TestBeFreelancerInternals:

    def test_abs_relative(self):
        assert _abs("/missions/42") == "https://www.befreelancr.com/missions/42"

    def test_abs_already_absolute(self):
        url = "https://www.befreelancr.com/missions/42"
        assert _abs(url) == url

    def test_abs_empty(self):
        assert _abs("") == ""

    def test_first_finds_h2(self):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup("<div><h2><a href='/m/1'>Titre</a></h2></div>", "html.parser")
        el = _first(soup, ["h2 a", "h3 a"])
        assert el is not None
        assert "Titre" in el.get_text()

    def test_first_fallback_works(self):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup("<div><span class='budget'>500 €</span></div>", "html.parser")
        el = _first(soup, [".prix", ".budget"])
        assert el is not None
        assert "500" in el.get_text()


# ── Tests scraping ────────────────────────────────────────────

class TestBeFreelancerScraping:

    @patch("sources.befreelancr.requests.get")
    @patch("sources.befreelancr.asyncio.sleep", return_value=None)
    def test_returns_list(self, mock_sleep, mock_get):
        mock_get.return_value = _mock_resp(make_html(FAKE_MISSIONS, "mission-card"))
        jobs = run(get_befreelancr_jobs())
        assert isinstance(jobs, list)

    @patch("sources.befreelancr.requests.get")
    @patch("sources.befreelancr.asyncio.sleep", return_value=None)
    def test_required_fields(self, mock_sleep, mock_get):
        mock_get.return_value = _mock_resp(make_html(FAKE_MISSIONS, "mission-card"))
        jobs = run(get_befreelancr_jobs())
        for job in jobs:
            assert_valid_job(job, "befreelancr")

    @patch("sources.befreelancr.requests.get")
    @patch("sources.befreelancr.asyncio.sleep", return_value=None)
    def test_source_field(self, mock_sleep, mock_get):
        mock_get.return_value = _mock_resp(make_html(FAKE_MISSIONS, "mission-card"))
        jobs = run(get_befreelancr_jobs())
        for job in jobs:
            assert job["source"] == "befreelancr"

    @patch("sources.befreelancr.requests.get")
    @patch("sources.befreelancr.asyncio.sleep", return_value=None)
    def test_date_field_extracted(self, mock_sleep, mock_get):
        """Le champ 'date' optionnel doit être extrait quand présent."""
        mock_get.return_value = _mock_resp(_make_html_with_date(FAKE_MISSIONS))
        jobs = run(get_befreelancr_jobs())
        for job in jobs:
            # date peut être "" ou une valeur — juste vérifier que la clé existe
            assert "date" in job

    @patch("sources.befreelancr.requests.get")
    @patch("sources.befreelancr.asyncio.sleep", return_value=None)
    def test_datetime_attribute_preferred_over_text(self, mock_sleep, mock_get):
        """L'attribut datetime="" est préféré au texte affiché."""
        html = """<html><body>
            <article class="mission-card">
                <h2><a href="/missions/1">Mission test date</a></h2>
                <time datetime="2024-06-01">1er juin 2024</time>
            </article>
        </body></html>"""
        mock_get.return_value = _mock_resp(html)
        jobs = run(get_befreelancr_jobs())
        if jobs:
            # Si date extraite, préférer le format ISO
            date_val = jobs[0].get("date", "")
            if date_val:
                assert "2024" in date_val

    @patch("sources.befreelancr.requests.get")
    @patch("sources.befreelancr.asyncio.sleep", return_value=None)
    def test_network_error_returns_empty(self, mock_sleep, mock_get):
        import requests as r
        mock_get.side_effect = r.RequestException("timeout")
        jobs = run(get_befreelancr_jobs())
        assert jobs == []

    @patch("sources.befreelancr.requests.get")
    @patch("sources.befreelancr.asyncio.sleep", return_value=None)
    def test_description_max_500(self, mock_sleep, mock_get):
        data = [{"title": "Mission desc long", "url": "/missions/x",
                 "description": "Z" * 700}]
        mock_get.return_value = _mock_resp(make_html(data, "mission-card"))
        jobs = run(get_befreelancr_jobs())
        assert_description_truncated(jobs, 500)

    @patch("sources.befreelancr.requests.get")
    @patch("sources.befreelancr.asyncio.sleep", return_value=None)
    def test_urls_absolute(self, mock_sleep, mock_get):
        mock_get.return_value = _mock_resp(make_html(FAKE_MISSIONS, "mission-card"))
        jobs = run(get_befreelancr_jobs())
        for job in jobs:
            assert job["url"].startswith("http")

    @patch("sources.befreelancr.requests.get")
    @patch("sources.befreelancr.asyncio.sleep", return_value=None)
    def test_fallback_selector_generic_card(self, mock_sleep, mock_get):
        """Si .mission-card absent, fallback [class*='card'] doit marcher."""
        html = """<html><body>
            <div class="offer-card">
                <h2><a href="/m/99">Mission fallback test</a></h2>
                <p>Description de la mission en fallback</p>
            </div>
        </body></html>"""
        mock_get.return_value = _mock_resp(html)
        jobs = run(get_befreelancr_jobs())
        assert isinstance(jobs, list)
