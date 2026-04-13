# =============================================================
# tests/phase2/test_upwork.py
# =============================================================

import asyncio, pytest
from unittest.mock import patch
from tests.phase2.conftest import make_rss, make_mock_response, assert_valid_job, assert_no_duplicates

def run(c): return asyncio.get_event_loop().run_until_complete(c)

FAKE_RSS_ITEMS = [
    {"title": "React Developer needed",     "link": "https://www.upwork.com/jobs/~01abc",
     "description": "Build a dashboard. <b>Budget: $500</b>. Skills: React, TypeScript."},
    {"title": "WordPress site refonte",     "link": "https://www.upwork.com/jobs/~02def",
     "description": "Refonte complète site. Hourly Rate: $30-$50/hr."},
    {"title": "SEO Expert freelance",       "link": "https://www.upwork.com/jobs/~03ghi",
     "description": "SEO audit and optimization. Budget: $300."},
]


class TestUpworkInternals:
    def test_clean_html_strips_tags(self):
        from sources.upwork import _clean_html
        assert "<b>" not in _clean_html("<b>Hello</b> world")
        assert "Hello world" in _clean_html("<b>Hello</b> world")

    def test_clean_html_max_500(self):
        from sources.upwork import _clean_html
        assert len(_clean_html("A" * 600)) <= 500

    def test_parse_budget_extracts_dollar(self):
        from sources.upwork import _parse_budget_from_desc
        result = _parse_budget_from_desc("Budget: $500 for this project")
        assert "$500" in result

    def test_parse_budget_extracts_hourly(self):
        from sources.upwork import _parse_budget_from_desc
        result = _parse_budget_from_desc("Hourly Rate: $25-$50 per hour")
        assert "$25" in result

    def test_parse_budget_empty_when_none(self):
        from sources.upwork import _parse_budget_from_desc
        assert _parse_budget_from_desc("No budget mentioned") == ""

    def test_rss_structure_valid(self):
        """make_rss doit générer du XML parseable."""
        import xml.etree.ElementTree as ET
        rss_bytes = make_rss(FAKE_RSS_ITEMS)
        root = ET.fromstring(rss_bytes)
        items = root.findall(".//item")
        assert len(items) == len(FAKE_RSS_ITEMS)


class TestUpworkScraping:

    @patch("sources.upwork.requests.get")
    @patch("sources.upwork.asyncio.sleep", return_value=None)
    def test_returns_list(self, _, mock_get):
        mock_get.return_value = make_mock_response(make_rss(FAKE_RSS_ITEMS))
        from sources.upwork import get_upwork_jobs
        jobs = run(get_upwork_jobs())
        assert isinstance(jobs, list)

    @patch("sources.upwork.requests.get")
    @patch("sources.upwork.asyncio.sleep", return_value=None)
    def test_required_fields(self, _, mock_get):
        mock_get.return_value = make_mock_response(make_rss(FAKE_RSS_ITEMS))
        from sources.upwork import get_upwork_jobs
        jobs = run(get_upwork_jobs())
        for job in jobs:
            assert_valid_job(job, "upwork")

    @patch("sources.upwork.requests.get")
    @patch("sources.upwork.asyncio.sleep", return_value=None)
    def test_no_duplicate_urls(self, _, mock_get):
        # Même RSS retourné pour chaque query → doublons à filtrer
        mock_get.return_value = make_mock_response(make_rss(FAKE_RSS_ITEMS))
        from sources.upwork import get_upwork_jobs
        jobs = run(get_upwork_jobs())
        assert_no_duplicates(jobs)

    @patch("sources.upwork.requests.get")
    @patch("sources.upwork.asyncio.sleep", return_value=None)
    def test_budget_extracted_from_description(self, _, mock_get):
        mock_get.return_value = make_mock_response(make_rss(FAKE_RSS_ITEMS))
        from sources.upwork import get_upwork_jobs
        jobs = run(get_upwork_jobs())
        budget_jobs = [j for j in jobs if j["budget_raw"]]
        assert len(budget_jobs) >= 1, "Au moins un job devrait avoir un budget extrait"

    @patch("sources.upwork.requests.get")
    @patch("sources.upwork.asyncio.sleep", return_value=None)
    def test_html_stripped_from_description(self, _, mock_get):
        mock_get.return_value = make_mock_response(make_rss(FAKE_RSS_ITEMS))
        from sources.upwork import get_upwork_jobs
        jobs = run(get_upwork_jobs())
        for job in jobs:
            assert "<" not in job["description"], f"HTML non nettoyé: {job['description'][:100]}"

    @patch("sources.upwork.requests.get")
    @patch("sources.upwork.asyncio.sleep", return_value=None)
    def test_network_error_returns_empty(self, _, mock_get):
        import requests as r
        mock_get.side_effect = r.RequestException("timeout")
        from sources.upwork import get_upwork_jobs
        jobs = run(get_upwork_jobs())
        assert isinstance(jobs, list)

    @patch("sources.upwork.requests.get")
    @patch("sources.upwork.asyncio.sleep", return_value=None)
    def test_invalid_xml_handled_gracefully(self, _, mock_get):
        mock_get.return_value = make_mock_response(b"<not valid xml>>>")
        from sources.upwork import get_upwork_jobs
        jobs = run(get_upwork_jobs())
        assert isinstance(jobs, list)

    @patch("sources.upwork.requests.get")
    @patch("sources.upwork.asyncio.sleep", return_value=None)
    def test_urls_are_absolute(self, _, mock_get):
        mock_get.return_value = make_mock_response(make_rss(FAKE_RSS_ITEMS))
        from sources.upwork import get_upwork_jobs
        jobs = run(get_upwork_jobs())
        for job in jobs:
            assert job["url"].startswith("http"), f"URL relative: {job['url']}"

    @patch("sources.upwork.requests.get")
    @patch("sources.upwork.asyncio.sleep", return_value=None)
    def test_multiple_queries_called(self, _, mock_get):
        """Le scraper doit interroger plusieurs queries RSS."""
        from sources.upwork import _QUERIES, get_upwork_jobs
        mock_get.return_value = make_mock_response(make_rss(FAKE_RSS_ITEMS))
        run(get_upwork_jobs())
        assert mock_get.call_count == len(_QUERIES)
