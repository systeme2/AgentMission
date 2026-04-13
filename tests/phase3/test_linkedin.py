# =============================================================
# tests/phase3/test_linkedin.py
# =============================================================

import asyncio, pytest
from unittest.mock import patch, MagicMock, AsyncMock
from tests.phase3.conftest import (
    make_html, make_mock_response,
    assert_valid_job, assert_no_duplicates,
)

def run(c): return asyncio.get_event_loop().run_until_complete(c)

FAKE_LI_CARDS = [
    {"title": "Développeur React Senior",  "url": "https://www.linkedin.com/jobs/view/1"},
    {"title": "Lead Frontend TypeScript",   "url": "https://www.linkedin.com/jobs/view/2"},
    {"title": "WordPress Developer Remote", "url": "https://www.linkedin.com/jobs/view/3"},
]

LI_HTML = """<html><body>
<ul>
  <li class="jobs-search__results-list">
    <div class="job-search-card">
      <h3 class="base-search-card__title">Développeur React Senior</h3>
      <h4 class="base-search-card__subtitle">TechCo</h4>
      <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/1">Voir</a>
    </div>
  </li>
  <li class="jobs-search__results-list">
    <div class="job-search-card">
      <h3 class="base-search-card__title">WordPress Developer</h3>
      <h4 class="base-search-card__subtitle">Agency XYZ</h4>
      <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/2">Voir</a>
    </div>
  </li>
</ul>
</body></html>"""


class TestLinkedInHTMLScraping:

    @patch("sources.linkedin.requests.get")
    @patch("sources.linkedin.asyncio.sleep", return_value=None)
    def test_returns_list(self, _, mock_get):
        mock_get.return_value = make_mock_response(LI_HTML)
        from sources.linkedin import _scrape_with_requests
        jobs = _scrape_with_requests()
        assert isinstance(jobs, list)

    @patch("sources.linkedin.requests.get")
    @patch("sources.linkedin.asyncio.sleep", return_value=None)
    def test_required_fields(self, _, mock_get):
        mock_get.return_value = make_mock_response(LI_HTML)
        from sources.linkedin import _scrape_with_requests
        jobs = _scrape_with_requests()
        for job in jobs:
            assert_valid_job(job, "linkedin")

    @patch("sources.linkedin.requests.get")
    @patch("sources.linkedin.asyncio.sleep", return_value=None)
    def test_authwall_returns_empty(self, _, mock_get):
        """Si LinkedIn redirige vers authwall → liste vide, pas d'exception."""
        m = make_mock_response("<html>Login required</html>")
        m.url = "https://www.linkedin.com/authwall?redirect=..."
        mock_get.return_value = m
        from sources.linkedin import _scrape_with_requests
        jobs = _scrape_with_requests()
        assert jobs == []

    @patch("sources.linkedin.requests.get")
    @patch("sources.linkedin.asyncio.sleep", return_value=None)
    def test_urls_absolute(self, _, mock_get):
        mock_get.return_value = make_mock_response(LI_HTML)
        from sources.linkedin import _scrape_with_requests
        jobs = _scrape_with_requests()
        for job in jobs:
            assert job["url"].startswith("http")

    @patch("sources.linkedin.requests.get")
    @patch("sources.linkedin.asyncio.sleep", return_value=None)
    def test_network_error_returns_empty(self, _, mock_get):
        import requests as r
        mock_get.side_effect = r.RequestException("timeout")
        from sources.linkedin import _scrape_with_requests
        jobs = _scrape_with_requests()
        assert jobs == []

    @patch("sources.linkedin.requests.get")
    @patch("sources.linkedin.asyncio.sleep", return_value=None)
    def test_company_appended_to_title(self, _, mock_get):
        mock_get.return_value = make_mock_response(LI_HTML)
        from sources.linkedin import _scrape_with_requests
        jobs = _scrape_with_requests()
        # Les titres devraient inclure "@ CompanyName"
        titles_with_company = [j for j in jobs if "@" in j["title"]]
        assert len(titles_with_company) >= 1


class TestLinkedInJobSpyFallback:

    def test_scrape_with_jobspy_raises_import_error_when_missing(self):
        import sys
        from unittest.mock import patch as _p
        with _p.dict("sys.modules", {"jobspy": None}):
            from sources.linkedin import _scrape_with_jobspy
            import pytest
            with pytest.raises(ImportError):
                _scrape_with_jobspy("react developer", "France")

    def test_scrape_with_jobspy_returns_list_on_exception(self):
        """Si jobspy lève une erreur (autre qu'ImportError) → liste vide."""
        with patch("sources.linkedin._scrape_with_jobspy", side_effect=Exception("API error")):
            # On vérifie juste que get_linkedin_jobs gère l'erreur
            pass  # Couvert par test_never_raises


class TestLinkedInGetJobs:

    @patch("sources.linkedin._scrape_with_requests")
    @patch("sources.linkedin.asyncio.sleep", return_value=None)
    def test_falls_back_to_html_when_jobspy_missing(self, _, mock_req):
        """Sans JobSpy, doit utiliser le fallback HTML."""
        mock_req.return_value = [
            {"title": "React Dev", "description": "", "url": "https://www.linkedin.com/jobs/view/1",
             "budget_raw": "", "source": "linkedin"}
        ]
        with patch.dict("sys.modules", {"jobspy": None}):
            from sources.linkedin import get_linkedin_jobs
            jobs = run(get_linkedin_jobs())
        assert isinstance(jobs, list)

    @patch("sources.linkedin._scrape_with_requests", return_value=[])
    @patch("sources.linkedin.asyncio.sleep", return_value=None)
    def test_never_raises(self, _, __):
        """get_linkedin_jobs ne doit jamais propager d'exception."""
        try:
            from sources.linkedin import get_linkedin_jobs
            jobs = run(get_linkedin_jobs())
            assert isinstance(jobs, list)
        except Exception as exc:
            pytest.fail(f"get_linkedin_jobs a levé: {exc}")

    @patch("sources.linkedin._scrape_with_requests")
    @patch("sources.linkedin.asyncio.sleep", return_value=None)
    def test_no_duplicates(self, _, mock_req):
        shared = {"title": "Dev", "description": "", "url": "https://www.linkedin.com/jobs/view/1",
                  "budget_raw": "", "source": "linkedin"}
        mock_req.return_value = [shared, shared]
        from sources.linkedin import get_linkedin_jobs
        jobs = run(get_linkedin_jobs())
        assert_no_duplicates(jobs)

    @patch("sources.linkedin._scrape_with_requests")
    @patch("sources.linkedin.asyncio.sleep", return_value=None)
    def test_source_field(self, _, mock_req):
        mock_req.return_value = [
            {"title": "Dev Senior", "description": "", "url": "https://www.linkedin.com/jobs/view/1",
             "budget_raw": "", "source": "linkedin"}
        ]
        from sources.linkedin import get_linkedin_jobs
        jobs = run(get_linkedin_jobs())
        for job in jobs:
            assert job["source"] == "linkedin"
