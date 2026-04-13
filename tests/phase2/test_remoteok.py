# =============================================================
# tests/phase2/test_remoteok.py
# =============================================================

import asyncio, pytest
from unittest.mock import patch
from tests.phase2.conftest import (
    make_remoteok_json, make_mock_response,
    assert_valid_job, assert_no_duplicates,
)

def run(c): return asyncio.get_event_loop().run_until_complete(c)


class TestRemoteOKInternals:
    def test_is_relevant_with_react_tag(self):
        from sources.remoteok import _is_relevant
        assert _is_relevant({"tags": ["react", "javascript"], "position": "Developer"})

    def test_is_relevant_with_position(self):
        from sources.remoteok import _is_relevant
        assert _is_relevant({"tags": ["other"], "position": "Web Developer"})

    def test_is_relevant_false_for_unrelated(self):
        from sources.remoteok import _is_relevant
        assert not _is_relevant({"tags": ["finance", "accounting"], "position": "CFO"})

    def test_format_salary_both(self):
        from sources.remoteok import _format_salary
        assert "$5000 – $7000" == _format_salary({"salary_min": 5000, "salary_max": 7000})

    def test_format_salary_min_only(self):
        from sources.remoteok import _format_salary
        assert "$3000+" == _format_salary({"salary_min": 3000, "salary_max": None})

    def test_format_salary_empty(self):
        from sources.remoteok import _format_salary
        assert "" == _format_salary({})


class TestRemoteOKScraping:

    @patch("sources.remoteok.requests.get")
    @patch("sources.remoteok.asyncio.sleep", return_value=None)
    def test_returns_list(self, _, mock_get):
        mock_get.return_value = make_mock_response(make_remoteok_json(3), content_type="application/json")
        from sources.remoteok import get_remoteok_jobs
        jobs = run(get_remoteok_jobs())
        assert isinstance(jobs, list)

    @patch("sources.remoteok.requests.get")
    @patch("sources.remoteok.asyncio.sleep", return_value=None)
    def test_required_fields(self, _, mock_get):
        mock_get.return_value = make_mock_response(make_remoteok_json(3), content_type="application/json")
        from sources.remoteok import get_remoteok_jobs
        jobs = run(get_remoteok_jobs())
        for job in jobs:
            assert_valid_job(job, "remoteok")

    @patch("sources.remoteok.requests.get")
    @patch("sources.remoteok.asyncio.sleep", return_value=None)
    def test_meta_header_skipped(self, _, mock_get):
        """Le premier élément (header légal) ne doit pas devenir un job."""
        mock_get.return_value = make_mock_response(make_remoteok_json(3), content_type="application/json")
        from sources.remoteok import get_remoteok_jobs
        jobs = run(get_remoteok_jobs())
        for job in jobs:
            assert "legal" not in job.get("title", "").lower()

    @patch("sources.remoteok.requests.get")
    @patch("sources.remoteok.asyncio.sleep", return_value=None)
    def test_irrelevant_jobs_filtered(self, _, mock_get):
        data = [
            {"legal": "notice"},
            {"position": "CFO", "company": "FinCorp", "tags": ["finance"],
             "url": "https://remoteok.com/jobs/1", "description": ""},
            {"position": "React Developer", "company": "TechCo", "tags": ["react"],
             "url": "https://remoteok.com/jobs/2", "description": ""},
        ]
        mock_get.return_value = make_mock_response(data, content_type="application/json")
        from sources.remoteok import get_remoteok_jobs
        jobs = run(get_remoteok_jobs())
        assert all("react" in j["title"].lower() or "react" in j["description"].lower()
                   or j["source"] == "remoteok" for j in jobs)
        assert not any("CFO" in j["title"] for j in jobs)

    @patch("sources.remoteok.requests.get")
    @patch("sources.remoteok.asyncio.sleep", return_value=None)
    def test_html_stripped_from_description(self, _, mock_get):
        mock_get.return_value = make_mock_response(make_remoteok_json(2), content_type="application/json")
        from sources.remoteok import get_remoteok_jobs
        jobs = run(get_remoteok_jobs())
        for job in jobs:
            assert "<" not in job["description"]

    @patch("sources.remoteok.requests.get")
    @patch("sources.remoteok.asyncio.sleep", return_value=None)
    def test_network_error_returns_empty(self, _, mock_get):
        import requests as r
        mock_get.side_effect = r.RequestException("timeout")
        from sources.remoteok import get_remoteok_jobs
        jobs = run(get_remoteok_jobs())
        assert jobs == []

    @patch("sources.remoteok.requests.get")
    @patch("sources.remoteok.asyncio.sleep", return_value=None)
    def test_salary_formatted(self, _, mock_get):
        mock_get.return_value = make_mock_response(make_remoteok_json(3), content_type="application/json")
        from sources.remoteok import get_remoteok_jobs
        jobs = run(get_remoteok_jobs())
        salary_jobs = [j for j in jobs if j["budget_raw"]]
        assert len(salary_jobs) >= 1
