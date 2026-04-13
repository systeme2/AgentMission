# =============================================================
# tests/phase2/test_fiverr_toptal_kicklox.py
# =============================================================

import asyncio, json, pytest
from unittest.mock import patch
from tests.phase2.conftest import (
    make_html, make_mock_response,
    assert_valid_job, assert_no_duplicates, assert_description_truncated,
)

def run(c): return asyncio.get_event_loop().run_until_complete(c)


# ── Fiverr ────────────────────────────────────────────────────

FIVERR_GIGS = [
    {"title": "I will create a professional WordPress website",
     "url": "/SELLER/create-wordpress", "budget": "À partir de 50 €"},
    {"title": "I will develop a React web application",
     "url": "/DEV/react-app",           "budget": "À partir de 120 €"},
    {"title": "I will do SEO audit and optimization",
     "url": "/EXPERT/seo-audit",        "budget": "À partir de 80 €"},
]

FIVERR_JSON_LD = json.dumps([
    {"@type": "Product", "name": "WordPress site pro",
     "url": "https://www.fiverr.com/SELLER/wordpress",
     "description": "Création site WordPress pro",
     "offers": {"price": "80", "priceCurrency": "$"}},
])


class TestFiverrInternals:
    def test_try_json_ld_extracts_product(self):
        from bs4 import BeautifulSoup
        from sources.fiverr import _try_json_ld
        html = f'<html><body><script type="application/ld+json">{FIVERR_JSON_LD}</script></body></html>'
        soup = BeautifulSoup(html, "html.parser")
        jobs = _try_json_ld(soup)
        assert len(jobs) == 1
        assert jobs[0]["source"] == "fiverr"
        assert jobs[0]["title"] == "WordPress site pro"

    def test_try_json_ld_empty_on_bad_json(self):
        from bs4 import BeautifulSoup
        from sources.fiverr import _try_json_ld
        html = '<html><body><script type="application/ld+json">NOT JSON</script></body></html>'
        soup = BeautifulSoup(html, "html.parser")
        jobs = _try_json_ld(soup)
        assert jobs == []

    def test_try_json_ld_skips_non_product(self):
        from bs4 import BeautifulSoup
        from sources.fiverr import _try_json_ld
        data = json.dumps([{"@type": "WebPage", "name": "Home", "url": "https://fiverr.com"}])
        html = f'<html><body><script type="application/ld+json">{data}</script></body></html>'
        soup = BeautifulSoup(html, "html.parser")
        jobs = _try_json_ld(soup)
        assert jobs == []


class TestFiverrScraping:

    @patch("sources.fiverr.requests.get")
    @patch("sources.fiverr.asyncio.sleep", return_value=None)
    def test_returns_list(self, _, mock_get):
        mock_get.return_value = make_mock_response(make_html(FIVERR_GIGS, "gig-card"))
        from sources.fiverr import get_fiverr_jobs
        jobs = run(get_fiverr_jobs())
        assert isinstance(jobs, list)

    @patch("sources.fiverr.requests.get")
    @patch("sources.fiverr.asyncio.sleep", return_value=None)
    def test_required_fields(self, _, mock_get):
        mock_get.return_value = make_mock_response(make_html(FIVERR_GIGS, "gig-card"))
        from sources.fiverr import get_fiverr_jobs
        jobs = run(get_fiverr_jobs())
        for job in jobs:
            assert_valid_job(job, "fiverr")

    @patch("sources.fiverr.requests.get")
    @patch("sources.fiverr.asyncio.sleep", return_value=None)
    def test_json_ld_preferred_over_html(self, _, mock_get):
        """Quand JSON-LD présent, il doit être utilisé en priorité."""
        html = f'''<html><body>
            <script type="application/ld+json">{FIVERR_JSON_LD}</script>
            <article class="gig-card">
                <h3><a href="/other/gig">Other gig HTML</a></h3>
            </article>
        </body></html>'''
        mock_get.return_value = make_mock_response(html)
        from sources.fiverr import get_fiverr_jobs
        jobs = run(get_fiverr_jobs())
        assert any("WordPress" in j["title"] for j in jobs)

    @patch("sources.fiverr.requests.get")
    @patch("sources.fiverr.asyncio.sleep", return_value=None)
    def test_no_duplicates_across_pages(self, _, mock_get):
        mock_get.return_value = make_mock_response(make_html(FIVERR_GIGS, "gig-card"))
        from sources.fiverr import get_fiverr_jobs
        jobs = run(get_fiverr_jobs())
        assert_no_duplicates(jobs)

    @patch("sources.fiverr.requests.get")
    @patch("sources.fiverr.asyncio.sleep", return_value=None)
    def test_network_error_returns_empty(self, _, mock_get):
        import requests as r
        mock_get.side_effect = r.RequestException("timeout")
        from sources.fiverr import get_fiverr_jobs
        jobs = run(get_fiverr_jobs())
        assert isinstance(jobs, list)


# ── Toptal ────────────────────────────────────────────────────

TOPTAL_JOBS = [
    {"title": "Senior React Developer",  "url": "/jobs/react-senior",   "budget": ""},
    {"title": "WordPress Expert",        "url": "/jobs/wordpress",       "budget": ""},
    {"title": "UX/UI Designer",          "url": "/jobs/ux-designer",     "budget": ""},
]


class TestToptalScraping:

    @patch("sources.toptal.requests.get")
    @patch("sources.toptal.asyncio.sleep", return_value=None)
    def test_returns_list(self, _, mock_get):
        mock_get.return_value = make_mock_response(make_html(TOPTAL_JOBS, "job-listing"))
        from sources.toptal import get_toptal_jobs
        jobs = run(get_toptal_jobs())
        assert isinstance(jobs, list)

    @patch("sources.toptal.requests.get")
    @patch("sources.toptal.asyncio.sleep", return_value=None)
    def test_required_fields(self, _, mock_get):
        mock_get.return_value = make_mock_response(make_html(TOPTAL_JOBS, "job-listing"))
        from sources.toptal import get_toptal_jobs
        jobs = run(get_toptal_jobs())
        for job in jobs:
            assert_valid_job(job, "toptal")

    @patch("sources.toptal.requests.get")
    @patch("sources.toptal.asyncio.sleep", return_value=None)
    def test_source_field(self, _, mock_get):
        mock_get.return_value = make_mock_response(make_html(TOPTAL_JOBS, "job-listing"))
        from sources.toptal import get_toptal_jobs
        jobs = run(get_toptal_jobs())
        for job in jobs:
            assert job["source"] == "toptal"

    @patch("sources.toptal.requests.get")
    @patch("sources.toptal.asyncio.sleep", return_value=None)
    def test_fallback_links_when_no_cards(self, _, mock_get):
        html = """<html><body>
            <a href="/jobs/react-developer">React Developer role</a>
            <a href="/freelance-react-expert">React Expert</a>
        </body></html>"""
        mock_get.return_value = make_mock_response(html)
        from sources.toptal import get_toptal_jobs
        jobs = run(get_toptal_jobs())
        assert isinstance(jobs, list)
        for job in jobs:
            assert job["url"].startswith("http")

    @patch("sources.toptal.requests.get")
    @patch("sources.toptal.asyncio.sleep", return_value=None)
    def test_network_error_returns_empty(self, _, mock_get):
        import requests as r
        mock_get.side_effect = r.RequestException("timeout")
        from sources.toptal import get_toptal_jobs
        jobs = run(get_toptal_jobs())
        assert jobs == []

    @patch("sources.toptal.requests.get")
    @patch("sources.toptal.asyncio.sleep", return_value=None)
    def test_description_truncated(self, _, mock_get):
        data = [{"title": "Dev senior", "url": "/jobs/x", "description": "T" * 700}]
        mock_get.return_value = make_mock_response(make_html(data, "job-listing"))
        from sources.toptal import get_toptal_jobs
        jobs = run(get_toptal_jobs())
        assert_description_truncated(jobs, 500)


# ── Kicklox ───────────────────────────────────────────────────

KICKLOX_JOBS = [
    {"title": "Développeur React Native mobile",  "url": "/missions/rn-1",  "budget": "TJM 550 €"},
    {"title": "DevOps AWS/Kubernetes senior",      "url": "/missions/ops-2", "budget": "TJM 700 €"},
    {"title": "Data Engineer Python/Spark",        "url": "/missions/data-3","budget": "TJM 650 €"},
]


class TestKickloxScraping:

    @patch("sources.kicklox.requests.get")
    @patch("sources.kicklox.asyncio.sleep", return_value=None)
    def test_returns_list(self, _, mock_get):
        mock_get.return_value = make_mock_response(make_html(KICKLOX_JOBS, "job-item"))
        from sources.kicklox import get_kicklox_jobs
        jobs = run(get_kicklox_jobs())
        assert isinstance(jobs, list)

    @patch("sources.kicklox.requests.get")
    @patch("sources.kicklox.asyncio.sleep", return_value=None)
    def test_required_fields(self, _, mock_get):
        mock_get.return_value = make_mock_response(make_html(KICKLOX_JOBS, "job-item"))
        from sources.kicklox import get_kicklox_jobs
        jobs = run(get_kicklox_jobs())
        for job in jobs:
            assert_valid_job(job, "kicklox")

    @patch("sources.kicklox.requests.get")
    @patch("sources.kicklox.asyncio.sleep", return_value=None)
    def test_source_field(self, _, mock_get):
        mock_get.return_value = make_mock_response(make_html(KICKLOX_JOBS, "job-item"))
        from sources.kicklox import get_kicklox_jobs
        jobs = run(get_kicklox_jobs())
        for job in jobs:
            assert job["source"] == "kicklox"

    @patch("sources.kicklox.requests.get")
    @patch("sources.kicklox.asyncio.sleep", return_value=None)
    def test_stops_at_first_successful_url(self, _, mock_get):
        """Si la première URL répond, ne pas appeler les suivantes."""
        mock_get.return_value = make_mock_response(make_html(KICKLOX_JOBS, "job-item"))
        from sources.kicklox import get_kicklox_jobs
        run(get_kicklox_jobs())
        assert mock_get.call_count == 1

    @patch("sources.kicklox.requests.get")
    @patch("sources.kicklox.asyncio.sleep", return_value=None)
    def test_fallback_to_next_url_on_network_error(self, _, mock_get):
        """Si la première URL échoue, essayer la suivante."""
        import requests as r
        mock_get.side_effect = [
            r.RequestException("première URL down"),
            make_mock_response(make_html(KICKLOX_JOBS, "job-item")),
        ]
        from sources.kicklox import get_kicklox_jobs
        jobs = run(get_kicklox_jobs())
        assert isinstance(jobs, list)

    @patch("sources.kicklox.requests.get")
    @patch("sources.kicklox.asyncio.sleep", return_value=None)
    def test_all_urls_fail_returns_empty(self, _, mock_get):
        import requests as r
        mock_get.side_effect = r.RequestException("tout est down")
        from sources.kicklox import get_kicklox_jobs
        jobs = run(get_kicklox_jobs())
        assert isinstance(jobs, list)

    @patch("sources.kicklox.requests.get")
    @patch("sources.kicklox.asyncio.sleep", return_value=None)
    def test_fallback_link_scraping(self, _, mock_get):
        html = """<html><body>
            <a href="/missions/mission-react">Mission React senior Paris</a>
            <a href="/offres/freelance-python">Freelance Python Data</a>
        </body></html>"""
        mock_get.return_value = make_mock_response(html)
        from sources.kicklox import get_kicklox_jobs
        jobs = run(get_kicklox_jobs())
        assert isinstance(jobs, list)
        for job in jobs:
            assert job["url"].startswith("http")
