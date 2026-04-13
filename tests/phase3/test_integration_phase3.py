# =============================================================
# tests/phase3/test_integration_phase3.py
# =============================================================

import asyncio, pytest
from tests.phase3.conftest import make_json_jobs, assert_valid_job, assert_no_duplicates

def run(c): return asyncio.get_event_loop().run_until_complete(c)

PHASE3_SOURCES = {"hackernews", "dev.to", "linkedin", "twitter", "indiehackers"}

ALL_SOURCES = {
    "codeur", "reddit", "welovedevs", "remixjobs",
    "freelance.com", "404works", "comeup", "befreelancr", "collective.work",
    "malt", "upwork", "remoteok", "freelancer.com",
    "fiverr", "toptal", "kicklox",
} | PHASE3_SOURCES


# ── 1. Enregistrement dans SOURCE_MAP ─────────────────────────

class TestSourceRegistrationPhase3:

    def test_all_phase3_in_source_map(self):
        from agents.collector import SOURCE_MAP
        for src in PHASE3_SOURCES:
            assert src in SOURCE_MAP, f"'{src}' manquant dans SOURCE_MAP"

    def test_all_phase3_callable(self):
        from agents.collector import SOURCE_MAP
        for src in PHASE3_SOURCES:
            fn = SOURCE_MAP.get(src)
            assert callable(fn), f"SOURCE_MAP['{src}'] non callable"

    def test_source_map_has_21_sources(self):
        from agents.collector import SOURCE_MAP
        assert len(SOURCE_MAP) >= 21, f"Attendu ≥21, obtenu {len(SOURCE_MAP)}: {list(SOURCE_MAP)}"

    def test_all_phase3_in_settings(self):
        from config.settings import settings
        enabled = set(settings.SOURCES_ENABLED)
        for src in PHASE3_SOURCES:
            assert src in enabled, f"'{src}' absent de SOURCES_ENABLED"

    def test_twitter_bearer_token_field_in_settings(self):
        from config.settings import settings
        assert hasattr(settings, "TWITTER_BEARER_TOKEN"), \
            "settings.TWITTER_BEARER_TOKEN absent — requis pour Twitter API"


# ── 2. Contrat de chaque source Phase 3 ──────────────────────

class TestSourceContractsPhase3:
    """Chaque source Phase 3 doit retourner [] sans exception sur erreur réseau."""

    SOURCES = [
        ("sources.hackernews",   "get_hackernews_jobs"),
        ("sources.devto",        "get_devto_jobs"),
        ("sources.linkedin",     "get_linkedin_jobs"),
        ("sources.twitter",      "get_twitter_jobs"),
        ("sources.indiehackers", "get_indiehackers_jobs"),
    ]

    @pytest.mark.parametrize("module,fn", SOURCES)
    def test_returns_list_type(self, module, fn):
        import importlib
        mod  = importlib.import_module(module)
        func = getattr(mod, fn)
        with _patch_all_requests(module), _patch_sleep(module):
            jobs = run(func())
        assert isinstance(jobs, list), f"[{module}.{fn}] doit retourner une liste"

    @pytest.mark.parametrize("module,fn", SOURCES)
    def test_never_raises_on_network_error(self, module, fn):
        import importlib, requests as r
        mod  = importlib.import_module(module)
        func = getattr(mod, fn)
        with _patch_all_requests(module, side_effect=r.RequestException("down")), \
             _patch_sleep(module):
            try:
                jobs = run(func())
                assert isinstance(jobs, list)
            except Exception as exc:
                pytest.fail(f"[{module}.{fn}] a levé sur erreur réseau: {exc}")


# ── 3. Filtrage spécifique par source ─────────────────────────

class TestPhase3Filtering:
    """Tests de logique métier : chaque source filtre correctement."""

    def test_hackernews_excludes_no_remote(self):
        from sources.hackernews import _is_relevant
        assert not _is_relevant("Senior developer, onsite only, no remote, New York")

    def test_hackernews_includes_react_remote(self):
        from sources.hackernews import _is_relevant
        assert _is_relevant("React developer | Remote | $120k | Full-time")

    def test_devto_excludes_tutorials(self):
        from sources.devto import _is_job_offer
        from tests.phase3.conftest import make_devto_article
        art = make_devto_article(1, "How I learned React in 30 days", "react")
        assert not _is_job_offer(art)

    def test_devto_includes_hiring_tag(self):
        from sources.devto import _is_job_offer
        from tests.phase3.conftest import make_devto_article
        art = make_devto_article(1, "Join our team!", "hiring")
        assert _is_job_offer(art)

    def test_twitter_irrelevant_tweet_returns_none(self):
        from sources.twitter import _tweet_to_job
        job = _tweet_to_job("1", "Just had a great weekend trip!")
        assert job is None

    def test_twitter_hiring_tweet_returns_job(self):
        from sources.twitter import _tweet_to_job
        job = _tweet_to_job("2", "We're hiring a remote React developer #hiring")
        assert job is not None

    def test_indiehackers_excludes_mrr_posts(self):
        from sources.indiehackers import _is_relevant
        assert not _is_relevant("My SaaS just hit $10k MRR milestone!")

    def test_indiehackers_includes_hiring(self):
        from sources.indiehackers import _is_relevant
        assert _is_relevant("Hiring: React developer needed for remote contract")


# ── 4. Collector 21 sources ───────────────────────────────────

class TestCollectorPhase3Integration:

    def _fake(self, n, name):
        jobs = make_json_jobs(n, name)
        async def _fn(): return jobs
        return _fn

    def _crash(self):
        async def _fn(): raise Exception("crash")
        return _fn

    def test_collector_aggregates_21_sources(self):
        from agents.collector import collect_jobs
        from config.settings import settings
        import agents.collector as col

        names    = list(ALL_SOURCES)
        fake_map = {n: self._fake(2, n) for n in names}

        orig_map, orig_en = col.SOURCE_MAP.copy(), settings.SOURCES_ENABLED[:]
        col.SOURCE_MAP       = fake_map
        settings.SOURCES_ENABLED = names
        try:
            jobs = run(collect_jobs())
        finally:
            col.SOURCE_MAP           = orig_map
            settings.SOURCES_ENABLED = orig_en

        assert len(jobs) == len(names) * 2, \
            f"Attendu {len(names)*2} jobs, obtenu {len(jobs)}"

    def test_collector_dedup_21_sources(self):
        from agents.collector import collect_jobs
        from config.settings import settings
        import agents.collector as col

        shared   = "https://example.com/same-job"
        dup      = [{"title": "Dup", "description": "", "url": shared,
                     "budget_raw": "", "source": "x"}]
        names    = list(ALL_SOURCES)
        async def _dup(): return dup
        fake_map = {n: _dup for n in names}

        orig_map, orig_en = col.SOURCE_MAP.copy(), settings.SOURCES_ENABLED[:]
        col.SOURCE_MAP       = fake_map
        settings.SOURCES_ENABLED = names
        try:
            jobs = run(collect_jobs())
        finally:
            col.SOURCE_MAP           = orig_map
            settings.SOURCES_ENABLED = orig_en

        assert [j["url"] for j in jobs].count(shared) == 1

    def test_collector_resilient_phase3_crashes(self):
        """Toutes les sources Phase 3 crashent → Phase 0+1+2 livrent quand même."""
        from agents.collector import collect_jobs
        from config.settings import settings
        import agents.collector as col

        names    = list(ALL_SOURCES)
        fake_map = {n: self._fake(2, n) for n in names}
        for src in PHASE3_SOURCES:
            fake_map[src] = self._crash()

        orig_map, orig_en = col.SOURCE_MAP.copy(), settings.SOURCES_ENABLED[:]
        col.SOURCE_MAP       = fake_map
        settings.SOURCES_ENABLED = names
        try:
            jobs = run(collect_jobs())
        finally:
            col.SOURCE_MAP           = orig_map
            settings.SOURCES_ENABLED = orig_en

        expected = (len(names) - len(PHASE3_SOURCES)) * 2
        assert len(jobs) >= expected, \
            f"Attendu ≥{expected} jobs après crash Phase 3, obtenu {len(jobs)}"

    def test_cross_source_dedup(self):
        """Un job présent sur HN ET LinkedIn → 1 seule occurrence."""
        from agents.collector import collect_jobs
        from config.settings import settings
        import agents.collector as col

        shared_url = "https://company.com/jobs/react-dev"
        hn_job  = [{"title": "React Dev @ HN",      "description": "", "url": shared_url,
                     "budget_raw": "", "source": "hackernews"}]
        li_job  = [{"title": "React Dev @ LinkedIn", "description": "", "url": shared_url,
                     "budget_raw": "", "source": "linkedin"}]

        names    = ["hackernews", "linkedin"]
        fake_map = {"hackernews": (lambda: asyncio.coroutine(lambda: hn_job)())
                                   if False else self._make_async(hn_job),
                    "linkedin":   self._make_async(li_job)}

        orig_map, orig_en = col.SOURCE_MAP.copy(), settings.SOURCES_ENABLED[:]
        col.SOURCE_MAP       = fake_map
        settings.SOURCES_ENABLED = names
        try:
            jobs = run(collect_jobs())
        finally:
            col.SOURCE_MAP           = orig_map
            settings.SOURCES_ENABLED = orig_en

        assert [j["url"] for j in jobs].count(shared_url) == 1

    def _make_async(self, data):
        async def _fn(): return data
        return _fn


# ── Helpers ───────────────────────────────────────────────────

from contextlib import contextmanager
from unittest.mock import patch as _patch

@contextmanager
def _patch_all_requests(module: str, **kwargs):
    """
    Patch requests.get dans le module ciblé pour bloquer le réseau.
    Pour les sources qui passent par asyncio.to_thread, on patche aussi
    les fonctions internes qui font les vraies requêtes.
    """
    import requests as r
    default_se = kwargs.get("side_effect", r.RequestException("mocked"))

    # Patch requests.get dans le module source
    with _patch(f"{module}.requests.get", side_effect=default_se):
        # Pour hackernews et devto qui utilisent to_thread,
        # on patche aussi les fonctions fetch internes
        extra_patches = []
        if "hackernews" in module:
            p1 = _patch(f"{module}._fetch_who_is_hiring_thread_id",
                        side_effect=r.RequestException("mocked"))
            p2 = _patch(f"{module}._fetch_jobs_from_thread",
                        side_effect=r.RequestException("mocked"))
            extra_patches = [p1.__enter__(), p2.__enter__()]
            try:
                yield
            finally:
                for p in [p1, p2]:
                    try: p.__exit__(None, None, None)
                    except Exception: pass
        elif "devto" in module:
            p1 = _patch(f"{module}._fetch_tag",
                        side_effect=r.RequestException("mocked"))
            extra_patches = [p1.__enter__()]
            try:
                yield
            finally:
                try: p1.__exit__(None, None, None)
                except Exception: pass
        else:
            yield

@contextmanager
def _patch_sleep(module: str):
    with _patch(f"{module}.asyncio.sleep", return_value=None):
        yield
