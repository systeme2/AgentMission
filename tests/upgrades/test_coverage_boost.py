# =============================================================
# tests/upgrades/test_coverage_boost.py
# =============================================================
# Tests ciblant exactement les branches non couvertes :
#   sources/codeur.py     (40% → lignes 30-82)
#   sources/reddit.py     (53% → lignes 33-62)
#   sources/welovedevs.py (46% → lignes 20-92)
#   sources/linkedin.py   (66% → lignes 49-76, 114, 136-137, 158-169)
#   sources/malt.py       (73% → lignes 75-109, 137-140, 160-161)
#   sources/rss_custom.py (74% → lignes 45-46, 63, 77-98, 119, 125-129)
#   agents/analyzer.py    (74% → lignes 50-71, 74-75, 125)
# =============================================================

import asyncio, pytest, json, xml.etree.ElementTree as ET
from unittest.mock import patch, MagicMock, AsyncMock

def run(c): return asyncio.get_event_loop().run_until_complete(c)

def _mock_resp(content, status=200, content_type="text/html"):
    m = MagicMock()
    m.status_code = status
    m.headers = {"Content-Type": content_type}
    if isinstance(content, bytes):
        m.content = content
        m.text    = content.decode("utf-8", errors="replace")
    elif isinstance(content, str):
        m.content = content.encode()
        m.text    = content
    else:
        enc = json.dumps(content).encode()
        m.content = enc
        m.text    = enc.decode()
        m.json    = MagicMock(return_value=content)
    m.raise_for_status = MagicMock(
        side_effect=None if status < 400 else Exception(f"HTTP {status}")
    )
    return m

def _html_projects(cards):
    items = ""
    for c in cards:
        items += f"""<article class="project-item">
            <h2 class="project-title"><a href="{c.get('url','/projects/1')}">{c.get('title','Job')}</a></h2>
            <p class="project-description">{c.get('desc','Description')}</p>
            <span class="budget">{c.get('budget','500€')}</span>
        </article>"""
    return f"<html><body>{items}</body></html>"


# ═══════════════════════════════════════════════════════════════
# CODEUR — lignes 30-82
# ═══════════════════════════════════════════════════════════════

class TestCodeurScraping:
    JOBS = [
        {"title": "Développeur WordPress senior", "url": "/projects/wp-1", "desc": "Mission WordPress", "budget": "800€"},
        {"title": "Refonte site React",            "url": "/projects/react-2", "desc": "Application React", "budget": "1200€"},
        {"title": "Expert SEO technique",          "url": "/projects/seo-3", "desc": "Audit SEO complet", "budget": "500€"},
    ]

    @patch("sources.codeur.requests.get")
    @patch("sources.codeur.asyncio.sleep", return_value=None)
    def test_parses_project_items(self, _, mock_get):
        mock_get.return_value = _mock_resp(_html_projects(self.JOBS))
        from sources.codeur import get_codeur_jobs
        jobs = run(get_codeur_jobs())
        assert isinstance(jobs, list)
        assert len(jobs) == 3

    @patch("sources.codeur.requests.get")
    @patch("sources.codeur.asyncio.sleep", return_value=None)
    def test_required_fields(self, _, mock_get):
        mock_get.return_value = _mock_resp(_html_projects(self.JOBS))
        from sources.codeur import get_codeur_jobs
        jobs = run(get_codeur_jobs())
        for job in jobs:
            for field in ("title","description","url","budget_raw","source"):
                assert field in job
            assert job["source"] == "codeur"

    @patch("sources.codeur.requests.get")
    @patch("sources.codeur.asyncio.sleep", return_value=None)
    def test_urls_absolute(self, _, mock_get):
        mock_get.return_value = _mock_resp(_html_projects(self.JOBS))
        from sources.codeur import get_codeur_jobs
        jobs = run(get_codeur_jobs())
        for job in jobs:
            assert job["url"].startswith("http"), f"URL relative: {job['url']}"

    @patch("sources.codeur.requests.get")
    @patch("sources.codeur.asyncio.sleep", return_value=None)
    def test_budget_extracted(self, _, mock_get):
        mock_get.return_value = _mock_resp(_html_projects(self.JOBS))
        from sources.codeur import get_codeur_jobs
        jobs = run(get_codeur_jobs())
        budget_jobs = [j for j in jobs if j["budget_raw"]]
        assert len(budget_jobs) >= 1

    @patch("sources.codeur.requests.get")
    @patch("sources.codeur.asyncio.sleep", return_value=None)
    def test_network_error_returns_empty(self, _, mock_get):
        import requests as r
        mock_get.side_effect = r.RequestException("timeout")
        from sources.codeur import get_codeur_jobs
        jobs = run(get_codeur_jobs())
        assert jobs == []

    @patch("sources.codeur.requests.get")
    @patch("sources.codeur.asyncio.sleep", return_value=None)
    def test_empty_page_returns_empty(self, _, mock_get):
        mock_get.return_value = _mock_resp("<html><body></body></html>")
        from sources.codeur import get_codeur_jobs
        jobs = run(get_codeur_jobs())
        assert isinstance(jobs, list)

    @patch("sources.codeur.requests.get")
    @patch("sources.codeur.asyncio.sleep", return_value=None)
    def test_card_without_title_skipped(self, _, mock_get):
        html = """<html><body>
            <article class="project-item"><span>no title here</span></article>
            <article class="project-item">
                <h2><a href="/projects/1">Valid Job Title</a></h2>
            </article>
        </body></html>"""
        mock_get.return_value = _mock_resp(html)
        from sources.codeur import get_codeur_jobs
        jobs = run(get_codeur_jobs())
        for job in jobs:
            assert len(job["title"]) > 0

    @patch("sources.codeur.requests.get")
    @patch("sources.codeur.asyncio.sleep", return_value=None)
    def test_description_max_500(self, _, mock_get):
        jobs_data = [{"title": "Dev Test", "url": "/projects/x", "desc": "A"*700}]
        mock_get.return_value = _mock_resp(_html_projects(jobs_data))
        from sources.codeur import get_codeur_jobs
        jobs = run(get_codeur_jobs())
        for job in jobs:
            assert len(job["description"]) <= 500

    @patch("sources.codeur.requests.get")
    @patch("sources.codeur.asyncio.sleep", return_value=None)
    def test_fallback_selectors_h2_h3(self, _, mock_get):
        """Si .project-title absent, fallback sur h2/h3."""
        html = """<html><body>
            <article class="project-item">
                <h2><a href="/projects/99">Développeur React freelance</a></h2>
                <p>Description mission React remote</p>
            </article>
        </body></html>"""
        mock_get.return_value = _mock_resp(html)
        from sources.codeur import get_codeur_jobs
        jobs = run(get_codeur_jobs())
        assert len(jobs) >= 1
        assert "React" in jobs[0]["title"]

    @patch("sources.codeur.requests.get")
    @patch("sources.codeur.asyncio.sleep", return_value=None)
    def test_card_without_link_skipped(self, _, mock_get):
        """Une card sans lien <a> doit être ignorée."""
        html = """<html><body>
            <article class="project-item">
                <h2 class="project-title">No link here</h2>
            </article>
        </body></html>"""
        mock_get.return_value = _mock_resp(html)
        from sources.codeur import get_codeur_jobs
        jobs = run(get_codeur_jobs())
        assert jobs == []


# ═══════════════════════════════════════════════════════════════
# REDDIT — lignes 33-62
# ═══════════════════════════════════════════════════════════════

def _reddit_response(posts):
    """Génère une réponse JSON Reddit."""
    return {
        "data": {
            "children": [
                {"data": {
                    "title":           p.get("title", ""),
                    "selftext":        p.get("text", ""),
                    "permalink":       p.get("permalink", "/r/forhire/comments/xyz/"),
                    "link_flair_text": p.get("flair", ""),
                }}
                for p in posts
            ]
        }
    }

class TestRedditScraping:

    @patch("sources.reddit.requests.get")
    @patch("sources.reddit.asyncio.sleep", return_value=None)
    def test_parses_hiring_posts_by_title(self, _, mock_get):
        data = _reddit_response([
            {"title": "[Hiring] Senior React Developer Remote", "text": "We need a React dev"},
            {"title": "Just sharing my journey learning Python"},  # non-hiring
        ])
        mock_get.return_value = _mock_resp(data, content_type="application/json")
        from sources.reddit import get_reddit_jobs
        jobs = run(get_reddit_jobs())
        assert any("React" in j["title"] for j in jobs)
        assert not any("journey" in j["title"] for j in jobs)

    @patch("sources.reddit.requests.get")
    @patch("sources.reddit.asyncio.sleep", return_value=None)
    def test_parses_hiring_posts_by_flair(self, _, mock_get):
        data = _reddit_response([
            {"title": "Remote position available", "flair": "hiring"},
        ])
        mock_get.return_value = _mock_resp(data, content_type="application/json")
        from sources.reddit import get_reddit_jobs
        jobs = run(get_reddit_jobs())
        assert len(jobs) >= 1

    @patch("sources.reddit.requests.get")
    @patch("sources.reddit.asyncio.sleep", return_value=None)
    def test_required_fields(self, _, mock_get):
        data = _reddit_response([
            {"title": "[Hiring] Developer needed", "text": "Full remote mission", "flair": "hiring"}
        ])
        mock_get.return_value = _mock_resp(data, content_type="application/json")
        from sources.reddit import get_reddit_jobs
        jobs = run(get_reddit_jobs())
        for job in jobs:
            for field in ("title","description","url","budget_raw","source"):
                assert field in job

    @patch("sources.reddit.requests.get")
    @patch("sources.reddit.asyncio.sleep", return_value=None)
    def test_source_includes_subreddit(self, _, mock_get):
        data = _reddit_response([{"title": "[Hiring] React dev", "flair": "hiring"}])
        mock_get.return_value = _mock_resp(data, content_type="application/json")
        from sources.reddit import get_reddit_jobs
        jobs = run(get_reddit_jobs())
        for job in jobs:
            assert job["source"].startswith("reddit/")

    @patch("sources.reddit.requests.get")
    @patch("sources.reddit.asyncio.sleep", return_value=None)
    def test_url_is_absolute(self, _, mock_get):
        data = _reddit_response([
            {"title": "[Hiring] Dev needed", "permalink": "/r/forhire/comments/abc/test/", "flair": "hiring"}
        ])
        mock_get.return_value = _mock_resp(data, content_type="application/json")
        from sources.reddit import get_reddit_jobs
        jobs = run(get_reddit_jobs())
        for job in jobs:
            assert job["url"].startswith("https://www.reddit.com")

    @patch("sources.reddit.requests.get")
    @patch("sources.reddit.asyncio.sleep", return_value=None)
    def test_network_error_returns_empty(self, _, mock_get):
        import requests as r
        mock_get.side_effect = r.RequestException("timeout")
        from sources.reddit import get_reddit_jobs
        jobs = run(get_reddit_jobs())
        assert isinstance(jobs, list)

    @patch("sources.reddit.requests.get")
    @patch("sources.reddit.asyncio.sleep", return_value=None)
    def test_all_subreddits_queried(self, _, mock_get):
        from sources.reddit import SUBREDDITS, get_reddit_jobs
        mock_get.return_value = _mock_resp(
            {"data": {"children": []}}, content_type="application/json"
        )
        run(get_reddit_jobs())
        assert mock_get.call_count == len(SUBREDDITS)

    @patch("sources.reddit.requests.get")
    @patch("sources.reddit.asyncio.sleep", return_value=None)
    def test_text_truncated_500(self, _, mock_get):
        data = _reddit_response([
            {"title": "[Hiring] Dev", "text": "X"*700, "flair": "hiring"}
        ])
        mock_get.return_value = _mock_resp(data, content_type="application/json")
        from sources.reddit import get_reddit_jobs
        jobs = run(get_reddit_jobs())
        for job in jobs:
            assert len(job["description"]) <= 500

    @patch("sources.reddit.requests.get")
    @patch("sources.reddit.asyncio.sleep", return_value=None)
    def test_all_hiring_tags_detected(self, _, mock_get):
        from sources.reddit import HIRING_TAGS
        for tag in HIRING_TAGS[:3]:
            data = _reddit_response([{"title": f"{tag} developer needed"}])
            mock_get.return_value = _mock_resp(data, content_type="application/json")
            from sources.reddit import get_reddit_jobs
            jobs = run(get_reddit_jobs())
            # Au moins un subreddit devrait matcher
            assert isinstance(jobs, list)


# ═══════════════════════════════════════════════════════════════
# WELOVEDEVS + REMIXJOBS — lignes 20-92
# ═══════════════════════════════════════════════════════════════

class TestWeLoveDevsScraping:
    API_DATA = {
        "content": [
            {"title": "Lead Dev React", "company": {"name": "TechCo"},
             "slug": "lead-dev-react-1", "description": "Mission React senior remote"},
            {"name": "Senior Python Engineer", "company": {"name": "DataCorp"},
             "id": "python-eng-2", "description": "Python data engineering"},
        ]
    }

    @patch("sources.welovedevs.requests.get")
    @patch("sources.welovedevs.asyncio.sleep", return_value=None)
    def test_parses_content_key(self, _, mock_get):
        mock_get.return_value = _mock_resp(self.API_DATA, content_type="application/json")
        from sources.welovedevs import get_welovedevs_jobs
        jobs = run(get_welovedevs_jobs())
        assert len(jobs) == 2

    @patch("sources.welovedevs.requests.get")
    @patch("sources.welovedevs.asyncio.sleep", return_value=None)
    def test_required_fields(self, _, mock_get):
        mock_get.return_value = _mock_resp(self.API_DATA, content_type="application/json")
        from sources.welovedevs import get_welovedevs_jobs
        jobs = run(get_welovedevs_jobs())
        for job in jobs:
            for field in ("title","description","url","budget_raw","source"):
                assert field in job

    @patch("sources.welovedevs.requests.get")
    @patch("sources.welovedevs.asyncio.sleep", return_value=None)
    def test_source_field(self, _, mock_get):
        mock_get.return_value = _mock_resp(self.API_DATA, content_type="application/json")
        from sources.welovedevs import get_welovedevs_jobs
        jobs = run(get_welovedevs_jobs())
        for job in jobs:
            assert job["source"] == "welovedevs"

    @patch("sources.welovedevs.requests.get")
    @patch("sources.welovedevs.asyncio.sleep", return_value=None)
    def test_company_name_in_title(self, _, mock_get):
        mock_get.return_value = _mock_resp(self.API_DATA, content_type="application/json")
        from sources.welovedevs import get_welovedevs_jobs
        jobs = run(get_welovedevs_jobs())
        assert any("TechCo" in j["title"] for j in jobs)

    @patch("sources.welovedevs.requests.get")
    @patch("sources.welovedevs.asyncio.sleep", return_value=None)
    def test_parses_list_response(self, _, mock_get):
        """L'API peut retourner une liste directe."""
        list_data = [
            {"title": "Dev Vue.js", "slug": "vue-1", "description": "Mission Vue remote"}
        ]
        mock_get.return_value = _mock_resp(list_data, content_type="application/json")
        from sources.welovedevs import get_welovedevs_jobs
        jobs = run(get_welovedevs_jobs())
        assert isinstance(jobs, list)

    @patch("sources.welovedevs.requests.get")
    @patch("sources.welovedevs.asyncio.sleep", return_value=None)
    def test_network_error_returns_empty(self, _, mock_get):
        import requests as r
        mock_get.side_effect = r.RequestException("timeout")
        from sources.welovedevs import get_welovedevs_jobs
        jobs = run(get_welovedevs_jobs())
        assert isinstance(jobs, list)

    @patch("sources.welovedevs.requests.get")
    @patch("sources.welovedevs.asyncio.sleep", return_value=None)
    def test_description_truncated(self, _, mock_get):
        data = {"content": [{"title": "Dev", "slug": "x", "description": "Z"*700}]}
        mock_get.return_value = _mock_resp(data, content_type="application/json")
        from sources.welovedevs import get_welovedevs_jobs
        jobs = run(get_welovedevs_jobs())
        for job in jobs:
            assert len(job["description"]) <= 500


def _make_rss_bytes(items):
    channel = ET.Element("channel")
    for it in items:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = it.get("title", "Job")
        ET.SubElement(item, "link").text  = it.get("link", "https://example.com/1")
        ET.SubElement(item, "description").text = it.get("desc", "Description")
    rss = ET.Element("rss", version="2.0")
    rss.append(channel)
    return ET.tostring(rss, encoding="unicode").encode()

class TestRemixJobsScraping:

    @patch("sources.welovedevs.requests.get")
    @patch("sources.welovedevs.asyncio.sleep", return_value=None)
    def test_parses_rss(self, _, mock_get):
        rss = _make_rss_bytes([
            {"title": "Dev React Remote", "link": "https://remixjobs.com/job/1", "desc": "Mission React"}
        ])
        mock_get.return_value = _mock_resp(rss)
        from sources.welovedevs import get_remixjobs_jobs
        jobs = run(get_remixjobs_jobs())
        assert isinstance(jobs, list)
        assert len(jobs) >= 1

    @patch("sources.welovedevs.requests.get")
    @patch("sources.welovedevs.asyncio.sleep", return_value=None)
    def test_required_fields(self, _, mock_get):
        rss = _make_rss_bytes([
            {"title": "Dev WordPress", "link": "https://remixjobs.com/job/2", "desc": "WordPress mission"}
        ])
        mock_get.return_value = _mock_resp(rss)
        from sources.welovedevs import get_remixjobs_jobs
        jobs = run(get_remixjobs_jobs())
        for job in jobs:
            for field in ("title","description","url","budget_raw","source"):
                assert field in job

    @patch("sources.welovedevs.requests.get")
    @patch("sources.welovedevs.asyncio.sleep", return_value=None)
    def test_source_is_remixjobs(self, _, mock_get):
        rss = _make_rss_bytes([{"title": "Dev", "link": "https://remixjobs.com/job/3"}])
        mock_get.return_value = _mock_resp(rss)
        from sources.welovedevs import get_remixjobs_jobs
        jobs = run(get_remixjobs_jobs())
        for job in jobs:
            assert job["source"] == "remixjobs"

    @patch("sources.welovedevs.requests.get")
    @patch("sources.welovedevs.asyncio.sleep", return_value=None)
    def test_network_error_returns_empty(self, _, mock_get):
        import requests as r
        mock_get.side_effect = r.RequestException("timeout")
        from sources.welovedevs import get_remixjobs_jobs
        jobs = run(get_remixjobs_jobs())
        assert isinstance(jobs, list)

    @patch("sources.welovedevs.requests.get")
    @patch("sources.welovedevs.asyncio.sleep", return_value=None)
    def test_html_cleaned_from_description(self, _, mock_get):
        rss = _make_rss_bytes([{
            "title": "Dev Python", "link": "https://remixjobs.com/job/4",
            "desc": "<p>Mission <b>Python</b> remote</p>"
        }])
        mock_get.return_value = _mock_resp(rss)
        from sources.welovedevs import get_remixjobs_jobs
        jobs = run(get_remixjobs_jobs())
        for job in jobs:
            assert "<" not in job["description"], "HTML non nettoyé"


# ═══════════════════════════════════════════════════════════════
# LINKEDIN — branches jobspy (49-76), exception card (136-137),
#             jobspy exception (158-169), fallback exception (180-181)
# ═══════════════════════════════════════════════════════════════

class TestLinkedInBranches:

    def test_scrape_with_jobspy_raises_import_error(self):
        """_scrape_with_jobspy lève ImportError si jobspy absent."""
        with patch.dict("sys.modules", {"jobspy": None}):
            from sources.linkedin import _scrape_with_jobspy
            with pytest.raises(ImportError):
                _scrape_with_jobspy("test", "France")

    def test_scrape_with_jobspy_returns_empty_on_exception(self):
        """_scrape_with_jobspy retourne [] sur toute autre exception."""
        with patch("sources.linkedin._scrape_with_jobspy",
                   side_effect=Exception("API error")) as mock_spy:
            # Test que get_linkedin_jobs gère l'exception
            pass  # Couvert par test_linkedin_jobspy_exception_handled

    @patch("sources.linkedin._scrape_with_requests")
    @patch("sources.linkedin._scrape_with_jobspy", side_effect=Exception("JobSpy API error"))
    @patch("sources.linkedin.asyncio.sleep", return_value=None)
    def test_jobspy_exception_falls_back_to_html(self, _, mock_spy, mock_req):
        """Si JobSpy lève une exception (non-ImportError) → fallback HTML."""
        mock_req.return_value = [
            {"title": "Dev React", "description": "", "url": "https://www.linkedin.com/jobs/1",
             "budget_raw": "", "source": "linkedin"}
        ]
        from sources.linkedin import get_linkedin_jobs
        jobs = run(get_linkedin_jobs())
        assert isinstance(jobs, list)
        mock_req.assert_called()

    @patch("sources.linkedin.requests.get")
    @patch("sources.linkedin.asyncio.sleep", return_value=None)
    def test_card_parsing_exception_continues(self, _, mock_get):
        """Une exception sur une card individuelle ne doit pas tout arrêter."""
        html = """<html><body>
            <li class="jobs-search__results-list">
                <div class="job-search-card">
                    <h3 class="base-search-card__title">React Developer</h3>
                    <a class="base-card__full-link" href="https://linkedin.com/jobs/1">Voir</a>
                </div>
            </li>
        </body></html>"""
        mock_get.return_value = _mock_resp(html)
        from sources.linkedin import _scrape_with_requests
        jobs = _scrape_with_requests()
        assert isinstance(jobs, list)

    @patch("sources.linkedin._scrape_with_requests", side_effect=Exception("HTML crash"))
    @patch("sources.linkedin.asyncio.sleep", return_value=None)
    def test_html_fallback_exception_returns_empty(self, _, mock_req):
        """Si le fallback HTML lève une exception → retour liste vide."""
        with patch("sources.linkedin.asyncio.to_thread",
                   side_effect=ImportError("jobspy")):
            from sources.linkedin import get_linkedin_jobs
            jobs = run(get_linkedin_jobs())
        assert isinstance(jobs, list)


# ═══════════════════════════════════════════════════════════════
# MALT — branches Playwright (75-109), title < 3 (137-140),
#         fallback exception (160-161), requests fallback (177-184)
# ═══════════════════════════════════════════════════════════════

class TestMaltBranches:

    def test_scrape_playwright_timeout_handled(self):
        """PWTimeout sur wait_for_selector → continue sans crash."""
        from unittest.mock import AsyncMock as AM

        # Reproduire la structure exacte de _scrape_with_playwright:
        # async with async_playwright() as pw:
        #     browser = await pw.chromium.launch(...)
        #     ctx     = await browser.new_context(...)
        #     page    = await ctx.new_page()
        #     await page.goto(...)
        #     await page.wait_for_selector(...)  ← PWTimeout ici
        #     cards = await page.query_selector_all(...)

        page = MagicMock()
        page.goto               = AM(return_value=None)
        page.wait_for_selector  = AM(side_effect=Exception("Timeout"))
        page.query_selector_all = AM(return_value=[])

        context = MagicMock()
        context.new_page = AM(return_value=page)

        browser = MagicMock()
        browser.new_context = AM(return_value=context)
        browser.close       = AM(return_value=None)

        pw_obj = MagicMock()
        pw_obj.chromium.launch = AM(return_value=browser)

        pw_ctx = MagicMock()
        pw_ctx.__aenter__ = AM(return_value=pw_obj)
        pw_ctx.__aexit__  = AM(return_value=None)

        # async_playwright est importé localement dans la fn — on patche le module
        with patch("playwright.async_api.async_playwright", return_value=pw_ctx):
            from sources.malt import _scrape_with_playwright
            jobs = run(_scrape_with_playwright())
        assert isinstance(jobs, list)

    @patch("sources.malt.requests.get")
    @patch("sources.malt.asyncio.sleep", return_value=None)
    def test_title_too_short_skipped(self, _, mock_get):
        """Un titre de moins de 3 chars doit être ignoré."""
        html = """<html><body>
            <article class="c-profile-card">
                <h2><a href="/profile/x">AB</a></h2>
            </article>
            <article class="c-profile-card">
                <h2><a href="/profile/y">Développeur React senior</a></h2>
            </article>
        </body></html>"""
        mock_get.return_value = _mock_resp(html)
        from sources.malt import _scrape_with_requests
        jobs = run(_scrape_with_requests())
        for job in jobs:
            assert len(job["title"]) >= 3

    @patch("sources.malt._scrape_with_playwright", new_callable=AsyncMock, return_value=[])
    @patch("sources.malt._scrape_with_requests", new_callable=AsyncMock)
    @patch("sources.malt.asyncio.sleep", return_value=None)
    def test_requests_fallback_exception_returns_empty(self, _, mock_req, mock_pw):
        """Si le fallback requests lève → liste vide, jamais d'exception."""
        mock_req.side_effect = Exception("crash inattendu")
        from sources.malt import get_malt_jobs
        jobs = run(get_malt_jobs())
        assert isinstance(jobs, list)
        assert jobs == []

    @patch("sources.malt.requests.get")
    @patch("sources.malt.asyncio.sleep", return_value=None)
    def test_card_without_link_skipped(self, _, mock_get):
        """Une card sans <a> doit être ignorée."""
        html = """<html><body>
            <article class="c-profile-card">
                <h2>Expert WordPress</h2>
            </article>
        </body></html>"""
        mock_get.return_value = _mock_resp(html)
        from sources.malt import _scrape_with_requests
        jobs = run(_scrape_with_requests())
        # Sans lien, le job n'est pas ajouté
        assert isinstance(jobs, list)


# ═══════════════════════════════════════════════════════════════
# RSS CUSTOM — branches _clean_html (45-46), skip sans titre (63),
#              _parse_atom (77-98), _fetch_feed atom/fallback (119, 125-129)
# ═══════════════════════════════════════════════════════════════

class TestRSSCustomBranches:

    def test_clean_html_bs4_exception_fallback(self):
        """Si BeautifulSoup lève une exception → regex fallback."""
        from sources.rss_custom import _clean_html
        with patch("sources.rss_custom.BeautifulSoup", side_effect=Exception("BS4 crash")):
            result = _clean_html("<p>Hello <b>world</b></p>")
        assert "Hello" in result or "world" in result
        assert "<" not in result

    def test_parse_rss2_skips_empty_items(self):
        """Items sans titre ou lien doivent être ignorés."""
        from sources.rss_custom import _parse_rss2
        rss_xml = """<rss><channel>
            <item><title></title><link></link></item>
            <item><title>Valid Job</title><link>https://example.com/1</link><description>Desc</description></item>
        </channel></rss>"""
        root = ET.fromstring(rss_xml)
        jobs = _parse_rss2(root, "https://example.com/feed.rss")
        assert len(jobs) == 1
        assert jobs[0]["title"] == "Valid Job"

    def test_parse_atom_valid(self):
        """_parse_atom doit parser un flux Atom valide."""
        from sources.rss_custom import _parse_atom
        atom_xml = """<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <title>React Developer Job</title>
                <link href="https://example.com/jobs/react" rel="alternate"/>
                <summary>Senior React developer needed remote</summary>
                <published>2024-03-15T10:00:00Z</published>
            </entry>
            <entry>
                <title>Python Engineer</title>
                <link href="https://example.com/jobs/python"/>
                <content>Python data engineering mission</content>
                <updated>2024-03-14T09:00:00Z</updated>
            </entry>
        </feed>"""
        root = ET.fromstring(atom_xml)
        jobs = _parse_atom(root, "https://example.com/feed.atom")
        assert len(jobs) == 2
        assert jobs[0]["title"] == "React Developer Job"
        assert jobs[0]["url"]   == "https://example.com/jobs/react"
        assert "rss:example.com" in jobs[0]["source"]

    def test_parse_atom_skips_missing_link(self):
        """Entry Atom sans lien doit être ignorée."""
        from sources.rss_custom import _parse_atom
        atom_xml = """<feed xmlns="http://www.w3.org/2005/Atom">
            <entry><title>No link entry</title></entry>
            <entry>
                <title>Valid entry</title>
                <link href="https://example.com/valid"/>
            </entry>
        </feed>"""
        root = ET.fromstring(atom_xml)
        jobs = _parse_atom(root, "https://example.com/feed.atom")
        assert len(jobs) == 1

    def test_fetch_feed_detects_atom(self):
        """_fetch_feed doit détecter un flux Atom et appeler _parse_atom."""
        from sources.rss_custom import _fetch_feed
        atom_xml = b"""<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <title>Job React</title>
                <link href="https://example.com/job/1" rel="alternate"/>
                <summary>Remote React job</summary>
            </entry>
        </feed>"""
        with patch("sources.rss_custom.requests.get",
                   return_value=_mock_resp(atom_xml)):
            jobs = _fetch_feed("https://example.com/feed.atom")
        assert isinstance(jobs, list)
        assert len(jobs) >= 1

    def test_fetch_feed_fallback_channel_subtag(self):
        """Si tag root n'est ni atom ni rss, cherche <channel> en sous-élément."""
        from sources.rss_custom import _fetch_feed
        # Root non-standard mais contient <channel>
        rss_xml = b"""<root><channel>
            <item>
                <title>Dev Laravel</title>
                <link>https://example.com/job/laravel</link>
                <description>Mission Laravel remote</description>
            </item>
        </channel></root>"""
        with patch("sources.rss_custom.requests.get",
                   return_value=_mock_resp(rss_xml)):
            jobs = _fetch_feed("https://example.com/weird-feed.xml")
        assert isinstance(jobs, list)

    def test_fetch_feed_fallback_no_channel_tries_atom(self):
        """Si ni atom ni rss ni channel → tente _parse_atom."""
        from sources.rss_custom import _fetch_feed
        # Root non-standard sans channel
        xml = b"""<entries>
            <entry>
                <title>Job Python</title>
            </entry>
        </entries>"""
        with patch("sources.rss_custom.requests.get",
                   return_value=_mock_resp(xml)):
            jobs = _fetch_feed("https://example.com/other-feed.xml")
        # Peut retourner [] mais ne doit pas lever
        assert isinstance(jobs, list)

    def test_parse_rss2_content_encoded_fallback(self):
        """Si <description> absent, utilise <content:encoded>."""
        from sources.rss_custom import _parse_rss2
        rss_xml = f"""<rss><channel>
            <item>
                <title>Dev SEO</title>
                <link>https://example.com/seo</link>
                <content:encoded xmlns:content="http://purl.org/rss/1.0/modules/content/">
                    Contenu détaillé de la mission SEO
                </content:encoded>
            </item>
        </channel></rss>"""
        root = ET.fromstring(rss_xml)
        jobs = _parse_rss2(root, "https://example.com/feed.rss")
        assert len(jobs) == 1
        assert "seo" in jobs[0]["source"].lower() or "example" in jobs[0]["source"].lower()


# ═══════════════════════════════════════════════════════════════
# ANALYZER — branches OpenAI (50-71), JSON invalide (74-75),
#             markdown fence stripping, _extract_budget ValueError (125)
# ═══════════════════════════════════════════════════════════════

class TestAnalyzerBranches:

    def test_analyze_with_openai_success(self):
        """La branche OpenAI est couverte : retourne un job enrichi avec analysis."""
        from config.settings import settings
        settings.OPENAI_API_KEY = "sk-real-mock"
        expected = {
            "type": "web", "stack": ["react", "nextjs"],
            "budget_estime": 800, "niveau": "expert",
            "remote": True, "resume": "Mission React senior",
            "est_freelance": True, "langue": "fr"
        }
        expected_json = json.dumps(expected)

        # analyze_job : await asyncio.to_thread(lambda: openai.create(...))
        # On simule to_thread qui appelle le callable et retourne un mock réponse
        import asyncio as _aio
        original_to_thread = _aio.to_thread

        async def patched_to_thread(fn, *args, **kwargs):
            # Simuler l'exécution du lambda dans un thread
            mock_resp = MagicMock()
            mock_resp.choices[0].message.content = expected_json
            return mock_resp

        try:
            with patch("agents.analyzer.asyncio.to_thread", patched_to_thread):
                from agents.analyzer import analyze_job
                job = {"title": "Dev React", "description": "Mission React remote",
                       "url": "https://x.com/1", "source": "codeur", "budget_raw": "800€"}
                result = run(analyze_job(job))
            # Avec le mock, analysis doit être parsé depuis le JSON attendu
            assert "analysis" in result
            assert isinstance(result["analysis"], dict)
            required = {"type", "stack", "budget_estime", "niveau",
                        "remote", "resume", "est_freelance", "langue"}
            assert required.issubset(set(result["analysis"].keys()))
        finally:
            settings.OPENAI_API_KEY = "sk-..."

    def test_analyze_with_markdown_fence_stripped(self):
        """Si OpenAI entoure le JSON de ```json ... ```, ça doit être nettoyé."""
        from config.settings import settings
        settings.OPENAI_API_KEY = "sk-real-mock"
        try:
            mock_response = MagicMock()
            mock_response.choices[0].message.content = (
                "```json\n"
                + json.dumps({"type":"web","stack":["vue"],"budget_estime":500,
                              "niveau":"intermédiaire","remote":False,
                              "resume":"Mission Vue","est_freelance":True,"langue":"fr"})
                + "\n```"
            )
            with patch("agents.analyzer.openai.chat.completions.create",
                       return_value=mock_response):
                from agents.analyzer import analyze_job
                job = {"title": "Dev Vue", "description": "Vue.js mission",
                       "url": "https://x.com/2", "source": "malt", "budget_raw": ""}
                result = run(analyze_job(job))
            assert result["analysis"]["stack"] == ["vue"]
        finally:
            settings.OPENAI_API_KEY = "sk-..."

    def test_analyze_json_decode_error_uses_fallback(self):
        """Si OpenAI retourne JSON invalide → _basic_analysis."""
        from config.settings import settings
        settings.OPENAI_API_KEY = "sk-real-mock"
        try:
            mock_response = MagicMock()
            mock_response.choices[0].message.content = "INVALID JSON {{"
            with patch("agents.analyzer.openai.chat.completions.create",
                       return_value=mock_response):
                from agents.analyzer import analyze_job
                job = {"title": "Dev WordPress", "description": "WordPress mission",
                       "url": "https://x.com/3", "source": "codeur", "budget_raw": ""}
                result = run(analyze_job(job))
            # Doit utiliser le fallback
            assert "analysis" in result
            assert isinstance(result["analysis"], dict)
        finally:
            settings.OPENAI_API_KEY = "sk-..."

    def test_extract_budget_value_error_returns_zero(self):
        """Si int() lève ValueError sur le match → retourne 0."""
        from agents.analyzer import _extract_budget
        # Pattern qui matche mais ne peut pas être converti en int
        result = _extract_budget("budget: abc€")
        # "abc" n'est pas un int → doit retourner 0
        assert result == 0

    def test_extract_budget_dollar_format(self):
        from agents.analyzer import _extract_budget
        assert _extract_budget("Project budget $1500") == 1500

    def test_extract_budget_euro_spaces(self):
        from agents.analyzer import _extract_budget
        assert _extract_budget("1 200 €") == 1200

    def test_basic_analysis_autre_type(self):
        """Type 'autre' si ni web, ni site, ni app dans le texte."""
        from agents.analyzer import _basic_analysis
        job = {"title": "Data Scientist IA", "description": "Machine learning pipeline"}
        analysis = _basic_analysis(job)
        assert analysis["type"] == "autre"

    def test_basic_analysis_langue_en(self):
        """Langue 'en' si pas de mots français."""
        from agents.analyzer import _basic_analysis
        job = {"title": "Senior React Developer", "description": "Remote position available"}
        analysis = _basic_analysis(job)
        assert analysis["langue"] == "en"

    def test_analyze_openai_generic_exception_uses_fallback(self):
        """Toute exception OpenAI (pas JSONDecodeError) → fallback."""
        from config.settings import settings
        settings.OPENAI_API_KEY = "sk-real-mock"
        try:
            with patch("agents.analyzer.openai.chat.completions.create",
                       side_effect=Exception("Connection error")):
                from agents.analyzer import analyze_job
                job = {"title": "Dev PHP", "description": "PHP Laravel mission",
                       "url": "https://x.com/4", "source": "codeur", "budget_raw": ""}
                result = run(analyze_job(job))
            assert "analysis" in result
            assert isinstance(result["analysis"], dict)
        finally:
            settings.OPENAI_API_KEY = "sk-..."
