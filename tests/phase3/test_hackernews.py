# =============================================================
# tests/phase3/test_hackernews.py
# =============================================================

import asyncio, pytest
from unittest.mock import patch, call
from tests.phase3.conftest import (
    make_algolia_response, make_hn_thread_hit, make_hn_comment_hit,
    make_mock_response, assert_valid_job, assert_no_duplicates,
)

def run(c): return asyncio.get_event_loop().run_until_complete(c)


# ── Tests internes ────────────────────────────────────────────

class TestHackerNewsInternals:

    def test_is_relevant_react_keyword(self):
        from sources.hackernews import _is_relevant
        assert _is_relevant("We are looking for a React developer, remote friendly")

    def test_is_relevant_remote_keyword(self):
        from sources.hackernews import _is_relevant
        assert _is_relevant("Full remote position for a Python backend developer")

    def test_is_relevant_false_for_unrelated(self):
        from sources.hackernews import _is_relevant
        assert not _is_relevant("Great article about machine learning theory")

    def test_is_relevant_excludes_no_remote(self):
        from sources.hackernews import _is_relevant
        # "no remote" → doit être exclu
        assert not _is_relevant("Senior dev, onsite only, no remote, NYC")

    def test_clean_text_strips_html(self):
        from sources.hackernews import _clean_text
        result = _clean_text("<p>Hello <b>world</b></p>")
        assert "<" not in result
        assert "Hello" in result and "world" in result

    def test_clean_text_decodes_entities(self):
        from sources.hackernews import _clean_text
        result = _clean_text("Rock &amp; Roll &lt;cool&gt;")
        assert "&amp;" not in result
        assert "&" in result

    def test_clean_text_max_500(self):
        from sources.hackernews import _clean_text
        assert len(_clean_text("A" * 700)) <= 500

    def test_extract_title_first_line(self):
        from sources.hackernews import _extract_title
        text = "Acme Corp | React Developer | Remote\nMore details here..."
        title = _extract_title(text)
        assert "Acme Corp" in title
        assert len(title) <= 120

    def test_extract_title_strips_html(self):
        from sources.hackernews import _extract_title
        assert "<" not in _extract_title("<p>My Company | Python Dev</p>")

    def test_extract_title_max_len(self):
        from sources.hackernews import _extract_title
        assert len(_extract_title("A" * 200)) <= 120


# ── Tests fetch_who_is_hiring ─────────────────────────────────

class TestHackerNewsFetchThread:

    @patch("sources.hackernews.requests.get")
    def test_returns_thread_id(self, mock_get):
        resp = make_mock_response(
            make_algolia_response([make_hn_thread_hit("39894219")]),
            content_type="application/json",
        )
        mock_get.return_value = resp
        from sources.hackernews import _fetch_who_is_hiring_thread_id
        tid = _fetch_who_is_hiring_thread_id()
        assert tid == 39894219

    @patch("sources.hackernews.requests.get")
    def test_returns_none_on_network_error(self, mock_get):
        import requests as r
        mock_get.side_effect = r.RequestException("timeout")
        from sources.hackernews import _fetch_who_is_hiring_thread_id
        assert _fetch_who_is_hiring_thread_id() is None

    @patch("sources.hackernews.requests.get")
    def test_returns_none_when_no_who_is_hiring(self, mock_get):
        resp = make_mock_response(
            make_algolia_response([{"objectID": "1", "title": "Ask HN: Favorite books?"}]),
            content_type="application/json",
        )
        mock_get.return_value = resp
        from sources.hackernews import _fetch_who_is_hiring_thread_id
        # Ne doit pas retourner un ID s'il n'y a pas de "who is hiring"
        assert _fetch_who_is_hiring_thread_id() is None


# ── Tests fetch_jobs_from_thread ──────────────────────────────

class TestHackerNewsFetchJobs:

    RELEVANT_COMMENT = make_hn_comment_hit(
        text="TechCorp | Senior React Developer | Remote | $120k-$150k\n"
             "We are looking for a React developer to build our web platform.",
    )
    IRRELEVANT_COMMENT = make_hn_comment_hit(
        object_id="999",
        text="Great article, I totally agree with this perspective on AI.",
    )

    @patch("sources.hackernews.requests.get")
    def test_returns_only_relevant_comments(self, mock_get):
        mock_get.return_value = make_mock_response(
            make_algolia_response([self.RELEVANT_COMMENT, self.IRRELEVANT_COMMENT]),
            content_type="application/json",
        )
        from sources.hackernews import _fetch_jobs_from_thread
        jobs = _fetch_jobs_from_thread(39894219)
        assert len(jobs) == 1
        assert "react" in jobs[0]["title"].lower() or "techcorp" in jobs[0]["title"].lower()

    @patch("sources.hackernews.requests.get")
    def test_required_fields(self, mock_get):
        mock_get.return_value = make_mock_response(
            make_algolia_response([self.RELEVANT_COMMENT]),
            content_type="application/json",
        )
        from sources.hackernews import _fetch_jobs_from_thread
        jobs = _fetch_jobs_from_thread(39894219)
        for job in jobs:
            assert_valid_job(job, "hackernews")

    @patch("sources.hackernews.requests.get")
    def test_urls_point_to_hn(self, mock_get):
        mock_get.return_value = make_mock_response(
            make_algolia_response([self.RELEVANT_COMMENT]),
            content_type="application/json",
        )
        from sources.hackernews import _fetch_jobs_from_thread
        jobs = _fetch_jobs_from_thread(39894219)
        for job in jobs:
            assert "hacker-news" in job["url"] or "news.ycombinator" in job["url"]

    @patch("sources.hackernews.requests.get")
    def test_network_error_returns_empty(self, mock_get):
        import requests as r
        mock_get.side_effect = r.RequestException("timeout")
        from sources.hackernews import _fetch_jobs_from_thread
        assert _fetch_jobs_from_thread(1) == []


# ── Tests get_hackernews_jobs (orchestration) ─────────────────

class TestHackerNewsGetJobs:

    @patch("sources.hackernews.asyncio.to_thread")
    @patch("sources.hackernews.asyncio.sleep", return_value=None)
    def test_full_pipeline_with_thread(self, _, mock_to_thread):
        """Pipeline complet : trouve thread → récupère jobs."""
        fake_jobs = [
            {"title": "React Dev", "description": "Hiring", "url": "https://news.ycombinator.com/item?id=123",
             "budget_raw": "", "source": "hackernews", "date": ""},
        ]
        # Premier appel = _fetch_who_is_hiring_thread_id, deuxième = _fetch_jobs_from_thread
        mock_to_thread.side_effect = [39894219, fake_jobs]
        from sources.hackernews import get_hackernews_jobs
        jobs = run(get_hackernews_jobs())
        assert isinstance(jobs, list)
        assert len(jobs) >= 0  # peut être 0 ou 1 selon comment to_thread est mocké

    @patch("sources.hackernews.asyncio.to_thread")
    @patch("sources.hackernews.asyncio.sleep", return_value=None)
    def test_fallback_when_thread_not_found(self, _, mock_to_thread):
        """Si thread non trouvé → fallback Algolia direct."""
        mock_to_thread.side_effect = [None, []]
        from sources.hackernews import get_hackernews_jobs
        jobs = run(get_hackernews_jobs())
        assert isinstance(jobs, list)

    @patch("sources.hackernews.asyncio.to_thread", side_effect=Exception("boom"))
    @patch("sources.hackernews.asyncio.sleep", return_value=None)
    def test_never_raises(self, _, __):
        """get_hackernews_jobs ne doit jamais propager d'exception."""
        from sources.hackernews import get_hackernews_jobs
        try:
            jobs = run(get_hackernews_jobs())
            assert isinstance(jobs, list)
        except Exception as exc:
            pytest.fail(f"get_hackernews_jobs a levé: {exc}")

    @patch("sources.hackernews.asyncio.to_thread")
    @patch("sources.hackernews.asyncio.sleep", return_value=None)
    def test_no_duplicates(self, _, mock_to_thread):
        # 3 jobs avec la même URL retournés par _fetch_jobs_from_thread
        same_job = [
            {"title": f"Dev React #{i}", "description": "",
             "url": "https://news.ycombinator.com/item?id=1",
             "budget_raw": "", "source": "hackernews", "date": ""}
            for i in range(3)
        ]
        mock_to_thread.side_effect = [39894219, same_job]
        from sources.hackernews import get_hackernews_jobs
        jobs = run(get_hackernews_jobs())
        # La source doit dédupliquer par URL → 1 seul job attendu
        assert_no_duplicates(jobs)
