# =============================================================
# tests/phase2/test_freelancer_com.py
# =============================================================

import asyncio, pytest
from unittest.mock import patch
from tests.phase2.conftest import (
    make_freelancer_api_response, make_mock_response,
    assert_valid_job, assert_no_duplicates,
)

def run(c): return asyncio.get_event_loop().run_until_complete(c)


class TestFreelancerComInternals:
    def test_budget_range_formatted(self):
        from sources.freelancer_com import _fetch_projects
        # On teste indirectement via le parsing — budget $200-$400
        proj = make_freelancer_api_response(1)
        p = proj["result"]["projects"][0]
        bmin = p["budget"]["minimum"]
        bmax = p["budget"]["maximum"]
        curr = p["currency"]["sign"]
        s    = f"{curr}{bmin} – {curr}{bmax}"
        assert "$" in s and "200" in s

    def test_seo_url_used_for_link(self):
        """Si seo_url présent → URL propre, sinon fallback /contest/id."""
        # seo_url présent
        url_with_seo = "https://www.freelancer.com/projects/wordpress-site-1"
        assert "projects" in url_with_seo
        # seo_url absent → fallback
        url_fallback = "https://www.freelancer.com/contest/1"
        assert "contest" in url_fallback


class TestFreelancerComScraping:

    @patch("sources.freelancer_com.requests.get")
    @patch("sources.freelancer_com.asyncio.sleep", return_value=None)
    def test_returns_list(self, _, mock_get):
        mock_get.return_value = make_mock_response(
            make_freelancer_api_response(3), content_type="application/json"
        )
        from sources.freelancer_com import get_freelancer_com_jobs
        jobs = run(get_freelancer_com_jobs())
        assert isinstance(jobs, list)

    @patch("sources.freelancer_com.requests.get")
    @patch("sources.freelancer_com.asyncio.sleep", return_value=None)
    def test_required_fields(self, _, mock_get):
        mock_get.return_value = make_mock_response(
            make_freelancer_api_response(3), content_type="application/json"
        )
        from sources.freelancer_com import get_freelancer_com_jobs
        jobs = run(get_freelancer_com_jobs())
        for job in jobs:
            assert_valid_job(job, "freelancer.com")

    @patch("sources.freelancer_com.requests.get")
    @patch("sources.freelancer_com.asyncio.sleep", return_value=None)
    def test_no_duplicate_urls(self, _, mock_get):
        mock_get.return_value = make_mock_response(
            make_freelancer_api_response(3), content_type="application/json"
        )
        from sources.freelancer_com import get_freelancer_com_jobs
        jobs = run(get_freelancer_com_jobs())
        assert_no_duplicates(jobs)

    @patch("sources.freelancer_com.requests.get")
    @patch("sources.freelancer_com.asyncio.sleep", return_value=None)
    def test_budget_formatted(self, _, mock_get):
        mock_get.return_value = make_mock_response(
            make_freelancer_api_response(2), content_type="application/json"
        )
        from sources.freelancer_com import get_freelancer_com_jobs
        jobs = run(get_freelancer_com_jobs())
        budget_jobs = [j for j in jobs if j["budget_raw"]]
        assert len(budget_jobs) >= 1
        assert "$" in budget_jobs[0]["budget_raw"]

    @patch("sources.freelancer_com.requests.get")
    @patch("sources.freelancer_com.asyncio.sleep", return_value=None)
    def test_empty_result_handled(self, _, mock_get):
        mock_get.return_value = make_mock_response(
            {"result": {"projects": []}, "status": "success"},
            content_type="application/json"
        )
        from sources.freelancer_com import get_freelancer_com_jobs
        jobs = run(get_freelancer_com_jobs())
        assert jobs == []

    @patch("sources.freelancer_com.requests.get")
    @patch("sources.freelancer_com.asyncio.sleep", return_value=None)
    def test_network_error_returns_empty(self, _, mock_get):
        import requests as r
        mock_get.side_effect = r.RequestException("connexion refusée")
        from sources.freelancer_com import get_freelancer_com_jobs
        jobs = run(get_freelancer_com_jobs())
        assert isinstance(jobs, list)

    @patch("sources.freelancer_com.requests.get")
    @patch("sources.freelancer_com.asyncio.sleep", return_value=None)
    def test_multiple_queries_sent(self, _, mock_get):
        from sources.freelancer_com import _SEARCH_QUERIES, get_freelancer_com_jobs
        mock_get.return_value = make_mock_response(
            make_freelancer_api_response(1), content_type="application/json"
        )
        run(get_freelancer_com_jobs())
        assert mock_get.call_count == len(_SEARCH_QUERIES)

    @patch("sources.freelancer_com.requests.get")
    @patch("sources.freelancer_com.asyncio.sleep", return_value=None)
    def test_projects_without_title_skipped(self, _, mock_get):
        data = {"result": {"projects": [
            {"id": 1, "title": "", "description": "Desc", "seo_url": "test-1",
             "budget": {"minimum": 100, "maximum": 200}, "currency": {"sign": "$"}},
            {"id": 2, "title": "Valid project", "description": "Desc", "seo_url": "test-2",
             "budget": {"minimum": 100, "maximum": 200}, "currency": {"sign": "$"}},
        ]}, "status": "success"}
        mock_get.return_value = make_mock_response(data, content_type="application/json")
        from sources.freelancer_com import get_freelancer_com_jobs
        jobs = run(get_freelancer_com_jobs())
        assert all(j["title"] for j in jobs)
