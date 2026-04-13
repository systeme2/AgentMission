# =============================================================
# tests/phase3/test_devto_indiehackers.py
# =============================================================

import asyncio, pytest
from unittest.mock import patch
from tests.phase3.conftest import (
    make_devto_article, make_mock_response, make_ih_nextdata,
    make_html, assert_valid_job, assert_no_duplicates, assert_description_truncated,
)

def run(c): return asyncio.get_event_loop().run_until_complete(c)


# ═══════════════════════════════════════════════════════════════
# DEV.TO
# ═══════════════════════════════════════════════════════════════

HIRING_ARTICLE    = make_devto_article(1, "We're hiring a React Developer (Remote)", "hiring")
NOT_HIRING_ARTICLE= make_devto_article(2, "My journey learning Python in 30 days",   "python")
FREELANCE_ARTICLE = make_devto_article(3, "Freelance position: WordPress developer needed", "freelance")


class TestDevToInternals:

    def test_is_job_offer_hiring_tag(self):
        from sources.devto import _is_job_offer
        art = make_devto_article(1, "Join our team!", "hiring")
        assert _is_job_offer(art)

    def test_is_job_offer_hiring_title(self):
        from sources.devto import _is_job_offer
        art = make_devto_article(1, "We're hiring a React developer", "webdev")
        assert _is_job_offer(art)

    def test_is_job_offer_false_for_tutorial(self):
        from sources.devto import _is_job_offer
        art = make_devto_article(1, "How I learned React in 30 days", "react")
        assert not _is_job_offer(art)

    def test_is_job_offer_excludes_available_for_hire(self):
        from sources.devto import _is_job_offer
        art = make_devto_article(1, "I am available for hire as a developer", "hiring")
        # Doit être exclu car c'est un freelance cherchant du travail
        assert not _is_job_offer(art)

    def test_fetch_tag_filters_correctly(self):
        from sources.devto import _fetch_tag
        articles = [HIRING_ARTICLE, NOT_HIRING_ARTICLE, FREELANCE_ARTICLE]
        mock_resp = make_mock_response(articles, content_type="application/json")
        with patch("sources.devto.requests.get", return_value=mock_resp):
            jobs = _fetch_tag("hiring")
        assert len(jobs) >= 1
        for job in jobs:
            assert_valid_job(job, "dev.to")

    def test_fetch_tag_network_error_returns_empty(self):
        from sources.devto import _fetch_tag
        import requests as r
        with patch("sources.devto.requests.get", side_effect=r.RequestException("timeout")):
            jobs = _fetch_tag("hiring")
        assert jobs == []


class TestDevToScraping:

    @patch("sources.devto.requests.get")
    @patch("sources.devto.asyncio.sleep", return_value=None)
    def test_returns_list(self, _, mock_get):
        mock_get.return_value = make_mock_response([HIRING_ARTICLE, FREELANCE_ARTICLE],
                                                    content_type="application/json")
        from sources.devto import get_devto_jobs
        jobs = run(get_devto_jobs())
        assert isinstance(jobs, list)

    @patch("sources.devto.requests.get")
    @patch("sources.devto.asyncio.sleep", return_value=None)
    def test_required_fields(self, _, mock_get):
        mock_get.return_value = make_mock_response([HIRING_ARTICLE],
                                                    content_type="application/json")
        from sources.devto import get_devto_jobs
        jobs = run(get_devto_jobs())
        for job in jobs:
            assert_valid_job(job, "dev.to")

    @patch("sources.devto.requests.get")
    @patch("sources.devto.asyncio.sleep", return_value=None)
    def test_no_duplicates_across_tags(self, _, mock_get):
        """Même article retourné par plusieurs tags → 1 seul en sortie."""
        mock_get.return_value = make_mock_response([HIRING_ARTICLE],
                                                    content_type="application/json")
        from sources.devto import get_devto_jobs
        jobs = run(get_devto_jobs())
        assert_no_duplicates(jobs)

    @patch("sources.devto.requests.get")
    @patch("sources.devto.asyncio.sleep", return_value=None)
    def test_multiple_tags_queried(self, _, mock_get):
        from sources.devto import _TAGS, get_devto_jobs
        mock_get.return_value = make_mock_response([], content_type="application/json")
        run(get_devto_jobs())
        assert mock_get.call_count == len(_TAGS)

    @patch("sources.devto.requests.get")
    @patch("sources.devto.asyncio.sleep", return_value=None)
    def test_network_error_returns_empty(self, _, mock_get):
        import requests as r
        mock_get.side_effect = r.RequestException("timeout")
        from sources.devto import get_devto_jobs
        jobs = run(get_devto_jobs())
        assert isinstance(jobs, list)

    @patch("sources.devto.requests.get")
    @patch("sources.devto.asyncio.sleep", return_value=None)
    def test_non_hiring_articles_filtered(self, _, mock_get):
        mock_get.return_value = make_mock_response(
            [NOT_HIRING_ARTICLE], content_type="application/json"
        )
        from sources.devto import get_devto_jobs
        jobs = run(get_devto_jobs())
        # NOT_HIRING_ARTICLE ne doit pas apparaître
        for job in jobs:
            assert "journey learning" not in job["title"].lower()

    @patch("sources.devto.requests.get")
    @patch("sources.devto.asyncio.sleep", return_value=None)
    def test_urls_absolute(self, _, mock_get):
        mock_get.return_value = make_mock_response([HIRING_ARTICLE],
                                                    content_type="application/json")
        from sources.devto import get_devto_jobs
        jobs = run(get_devto_jobs())
        for job in jobs:
            assert job["url"].startswith("http")


# ═══════════════════════════════════════════════════════════════
# INDIEHACKERS
# ═══════════════════════════════════════════════════════════════

IH_JOBS_DATA = [
    {"title": "Hiring: React Developer (Remote)", "url": "/jobs/react-dev",
     "description": "We are hiring a remote React developer.", "salary": ""},
    {"title": "Node.js Backend Engineer needed", "url": "https://www.indiehackers.com/jobs/nodejs",
     "description": "Contract position, remote-friendly.", "salary": "5000"},
]


class TestIndieHackersInternals:

    def test_is_relevant_hiring_keyword(self):
        from sources.indiehackers import _is_relevant
        assert _is_relevant("We're hiring a remote developer")

    def test_is_relevant_job_keyword(self):
        from sources.indiehackers import _is_relevant
        assert _is_relevant("Contract position for frontend developer")

    def test_is_relevant_false_for_unrelated(self):
        from sources.indiehackers import _is_relevant
        assert not _is_relevant("My SaaS just hit $10k MRR milestone")

    def test_parse_next_data_extracts_jobs(self):
        from bs4 import BeautifulSoup
        from sources.indiehackers import _parse_next_data
        html = make_ih_nextdata(IH_JOBS_DATA)
        soup = BeautifulSoup(html, "html.parser")
        jobs = _parse_next_data(soup)
        assert len(jobs) >= 1
        for job in jobs:
            assert job["source"] == "indiehackers"

    def test_parse_next_data_handles_missing_script(self):
        from bs4 import BeautifulSoup
        from sources.indiehackers import _parse_next_data
        soup = BeautifulSoup("<html><body></body></html>", "html.parser")
        assert _parse_next_data(soup) == []

    def test_parse_next_data_handles_invalid_json(self):
        from bs4 import BeautifulSoup
        from sources.indiehackers import _parse_next_data
        html = '<html><body><script id="__NEXT_DATA__" type="application/json">INVALID</script></body></html>'
        soup = BeautifulSoup(html, "html.parser")
        assert _parse_next_data(soup) == []

    def test_abs_relative_path(self):
        from sources.indiehackers import _abs
        assert _abs("/jobs/test") == "https://www.indiehackers.com/jobs/test"

    def test_abs_already_absolute(self):
        from sources.indiehackers import _abs
        url = "https://www.indiehackers.com/jobs/test"
        assert _abs(url) == url


class TestIndieHackersScraping:

    @patch("sources.indiehackers.requests.get")
    @patch("sources.indiehackers.asyncio.sleep", return_value=None)
    def test_uses_next_data_when_available(self, _, mock_get):
        html = make_ih_nextdata(IH_JOBS_DATA)
        mock_get.return_value = make_mock_response(html)
        from sources.indiehackers import get_indiehackers_jobs
        jobs = run(get_indiehackers_jobs())
        assert isinstance(jobs, list)
        for job in jobs:
            assert job["source"] == "indiehackers"

    @patch("sources.indiehackers.requests.get")
    @patch("sources.indiehackers.asyncio.sleep", return_value=None)
    def test_required_fields(self, _, mock_get):
        html = make_ih_nextdata(IH_JOBS_DATA)
        mock_get.return_value = make_mock_response(html)
        from sources.indiehackers import get_indiehackers_jobs
        jobs = run(get_indiehackers_jobs())
        for job in jobs:
            assert_valid_job(job, "indiehackers")

    @patch("sources.indiehackers.requests.get")
    @patch("sources.indiehackers.asyncio.sleep", return_value=None)
    def test_html_fallback_when_no_next_data(self, _, mock_get):
        html = make_html(
            [{"title": "Hiring React dev remote", "url": "/jobs/react"}],
            "job-listing",
        )
        mock_get.return_value = make_mock_response(html)
        from sources.indiehackers import get_indiehackers_jobs
        jobs = run(get_indiehackers_jobs())
        assert isinstance(jobs, list)

    @patch("sources.indiehackers.requests.get")
    @patch("sources.indiehackers.asyncio.sleep", return_value=None)
    def test_link_fallback(self, _, mock_get):
        """Fallback sur liens directs /jobs/ si pas de cards."""
        html = """<html><body>
            <a href="/jobs/react-remote">Hiring React Developer Remote</a>
            <a href="/jobs/backend-contract">Backend Contract Position</a>
        </body></html>"""
        mock_get.return_value = make_mock_response(html)
        from sources.indiehackers import get_indiehackers_jobs
        jobs = run(get_indiehackers_jobs())
        assert isinstance(jobs, list)
        for job in jobs:
            assert job["url"].startswith("http")

    @patch("sources.indiehackers.requests.get")
    @patch("sources.indiehackers.asyncio.sleep", return_value=None)
    def test_stops_at_first_productive_url(self, _, mock_get):
        html = make_ih_nextdata(IH_JOBS_DATA)
        mock_get.return_value = make_mock_response(html)
        from sources.indiehackers import get_indiehackers_jobs
        run(get_indiehackers_jobs())
        # Si la première URL est productive, on s'arrête là
        assert mock_get.call_count == 1

    @patch("sources.indiehackers.requests.get")
    @patch("sources.indiehackers.asyncio.sleep", return_value=None)
    def test_network_error_returns_empty(self, _, mock_get):
        import requests as r
        mock_get.side_effect = r.RequestException("timeout")
        from sources.indiehackers import get_indiehackers_jobs
        jobs = run(get_indiehackers_jobs())
        assert isinstance(jobs, list)

    @patch("sources.indiehackers.requests.get")
    @patch("sources.indiehackers.asyncio.sleep", return_value=None)
    def test_non_relevant_posts_filtered(self, _, mock_get):
        """Les posts sans mots-clés hiring doivent être filtrés."""
        data = [
            {"title": "My SaaS just hit $10k MRR!",
             "url":   "/posts/saas-mrr", "description": "Revenue milestone achieved."},
            {"title": "Hiring: Python developer needed",
             "url":   "/jobs/python-dev", "description": "Remote contract position."},
        ]
        mock_get.return_value = make_mock_response(make_ih_nextdata(data))
        from sources.indiehackers import get_indiehackers_jobs
        jobs = run(get_indiehackers_jobs())
        for job in jobs:
            assert "saas" not in job["title"].lower() or "hiring" in job["title"].lower()

    @patch("sources.indiehackers.requests.get")
    @patch("sources.indiehackers.asyncio.sleep", return_value=None)
    def test_description_truncated(self, _, mock_get):
        data = [{"title": "Hiring dev",
                 "url": "/jobs/x",
                 "description": "D" * 700}]
        mock_get.return_value = make_mock_response(make_ih_nextdata(data))
        from sources.indiehackers import get_indiehackers_jobs
        jobs = run(get_indiehackers_jobs())
        assert_description_truncated(jobs, 500)
