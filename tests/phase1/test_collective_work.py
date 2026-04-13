# =============================================================
# tests/phase1/test_collective_work.py
# =============================================================

import asyncio
import json
import pytest
from unittest.mock import patch, MagicMock

from tests.phase1.conftest import (
    make_html, assert_valid_job,
    assert_no_duplicates, assert_description_truncated,
)
from sources.collective_work import (
    get_collective_work_jobs,
    _abs, _first, _parse_json_response,
)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


FAKE_JOBS_HTML = [
    {"title": "Lead Dev React / TypeScript",         "url": "/jobs/react-lead-1",  "budget": "TJM 650 €"},
    {"title": "Architecte Cloud AWS freelance",      "url": "/jobs/cloud-arch-2",  "budget": "TJM 750 €"},
    {"title": "Product Designer UX senior",          "url": "/jobs/ux-design-3",   "budget": "TJM 500 €"},
]

FAKE_API_RESPONSE = {
    "jobs": [
        {"title": "Backend Python Django",  "url": "/jobs/py-1",   "description": "Mission Python", "salary": "600 €/j", "company": "Startup A"},
        {"title": "Frontend Vue.js senior", "url": "/jobs/vue-2",  "description": "Mission Vue",    "salary": "550 €/j", "company": "Scale-up B"},
        {"title": "DevOps Kubernetes",      "slug": "devops-k8s-3","description": "Mission K8s",    "salary": "700 €/j", "company": ""},
    ]
}


def _mock_resp(content, status=200, content_type="text/html"):
    m = MagicMock()
    m.status_code = status
    m.headers = {"Content-Type": content_type}
    if isinstance(content, str):
        m.text = content
    else:
        m.text = json.dumps(content)
        m.json = MagicMock(return_value=content)
    m.raise_for_status = MagicMock(
        side_effect=None if status == 200 else Exception(f"HTTP {status}")
    )
    return m


def _make_nextjs_html(jobs: list) -> str:
    """HTML avec __NEXT_DATA__ embarqué (comme Next.js)."""
    payload = {
        "props": {
            "pageProps": {
                "jobs": [
                    {
                        "title": j.get("title", ""),
                        "url":   j.get("url", ""),
                        "description": j.get("description", ""),
                        "salary": j.get("budget", ""),
                    }
                    for j in jobs
                ]
            }
        }
    }
    return f"""<!DOCTYPE html>
<html><body>
<script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script>
</body></html>"""


# ── Tests internes ────────────────────────────────────────────

class TestCollectiveWorkInternals:

    def test_abs_relative(self):
        assert _abs("/jobs/1") == "https://collective.work/jobs/1"

    def test_abs_absolute(self):
        url = "https://collective.work/jobs/1"
        assert _abs(url) == url

    def test_abs_empty(self):
        assert _abs("") == ""

    def test_parse_json_list(self):
        data = [
            {"title": "Dev Python", "url": "https://collective.work/jobs/1",
             "description": "Mission Python", "salary": "600€"},
        ]
        jobs = _parse_json_response(data)
        assert len(jobs) == 1
        assert jobs[0]["title"] == "Dev Python"
        assert jobs[0]["source"] == "collective.work"

    def test_parse_json_dict_with_jobs_key(self):
        data = {"jobs": FAKE_API_RESPONSE["jobs"]}
        jobs = _parse_json_response(data)
        assert len(jobs) == 3

    def test_parse_json_slug_fallback_for_url(self):
        """Si 'url' absent, le slug doit être utilisé pour construire l'URL."""
        data = [{"title": "Test", "slug": "my-job-123", "description": ""}]
        jobs = _parse_json_response(data)
        assert len(jobs) == 1
        assert "my-job-123" in jobs[0]["url"]

    def test_parse_json_with_company(self):
        data = [{"title": "Dev React", "url": "/jobs/1", "company": "Acme Corp"}]
        jobs = _parse_json_response(data)
        assert len(jobs) == 1
        assert "Acme Corp" in jobs[0]["title"]

    def test_parse_json_empty_list(self):
        jobs = _parse_json_response([])
        assert jobs == []

    def test_parse_json_dict_no_known_key(self):
        jobs = _parse_json_response({"random": "data"})
        assert jobs == []

    def test_parse_json_max_30_items(self):
        data = [{"title": f"Job {i}", "url": f"/jobs/{i}"} for i in range(50)]
        jobs = _parse_json_response(data)
        assert len(jobs) <= 30


# ── Tests scraping HTML ───────────────────────────────────────

class TestCollectiveWorkHTMLScraping:

    @patch("sources.collective_work.requests.get")
    @patch("sources.collective_work.asyncio.sleep", return_value=None)
    def test_returns_list(self, mock_sleep, mock_get):
        mock_get.return_value = _mock_resp(make_html(FAKE_JOBS_HTML, "job-card"))
        jobs = run(get_collective_work_jobs())
        assert isinstance(jobs, list)

    @patch("sources.collective_work.requests.get")
    @patch("sources.collective_work.asyncio.sleep", return_value=None)
    def test_required_fields(self, mock_sleep, mock_get):
        mock_get.return_value = _mock_resp(make_html(FAKE_JOBS_HTML, "job-card"))
        jobs = run(get_collective_work_jobs())
        for job in jobs:
            assert_valid_job(job, "collective.work")

    @patch("sources.collective_work.requests.get")
    @patch("sources.collective_work.asyncio.sleep", return_value=None)
    def test_description_truncated(self, mock_sleep, mock_get):
        data = [{"title": "Dev senior", "url": "/jobs/x", "description": "Y" * 700}]
        mock_get.return_value = _mock_resp(make_html(data, "job-card"))
        jobs = run(get_collective_work_jobs())
        assert_description_truncated(jobs, 500)

    @patch("sources.collective_work.requests.get")
    @patch("sources.collective_work.asyncio.sleep", return_value=None)
    def test_urls_absolute(self, mock_sleep, mock_get):
        mock_get.return_value = _mock_resp(make_html(FAKE_JOBS_HTML, "job-card"))
        jobs = run(get_collective_work_jobs())
        for job in jobs:
            assert job["url"].startswith("http")

    @patch("sources.collective_work.requests.get")
    @patch("sources.collective_work.asyncio.sleep", return_value=None)
    def test_network_error_returns_empty(self, mock_sleep, mock_get):
        import requests as r
        mock_get.side_effect = r.RequestException("timeout")
        jobs = run(get_collective_work_jobs())
        assert jobs == []


# ── Tests JSON API ────────────────────────────────────────────

class TestCollectiveWorkAPIFallback:

    @patch("sources.collective_work.requests.get")
    @patch("sources.collective_work.asyncio.sleep", return_value=None)
    def test_json_api_used_when_available(self, mock_sleep, mock_get):
        """Si l'API JSON répond, on doit l'utiliser et arrêter là."""
        api_resp = _mock_resp(FAKE_API_RESPONSE, content_type="application/json")
        mock_get.return_value = api_resp
        jobs = run(get_collective_work_jobs())
        assert len(jobs) == 3
        for job in jobs:
            assert_valid_job(job, "collective.work")

    @patch("sources.collective_work.requests.get")
    @patch("sources.collective_work.asyncio.sleep", return_value=None)
    def test_nextjs_data_extracted(self, mock_sleep, mock_get):
        """Le JSON __NEXT_DATA__ doit être extrait si l'API échoue."""
        html = _make_nextjs_html(FAKE_JOBS_HTML)
        mock_get.return_value = _mock_resp(html)
        jobs = run(get_collective_work_jobs())
        assert isinstance(jobs, list)

    @patch("sources.collective_work.requests.get")
    @patch("sources.collective_work.asyncio.sleep", return_value=None)
    def test_json_api_jobs_have_correct_source(self, mock_sleep, mock_get):
        api_resp = _mock_resp(FAKE_API_RESPONSE, content_type="application/json")
        mock_get.return_value = api_resp
        jobs = run(get_collective_work_jobs())
        for job in jobs:
            assert job["source"] == "collective.work"
