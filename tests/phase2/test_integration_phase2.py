# =============================================================
# tests/phase2/test_integration_phase2.py
# =============================================================

import asyncio, pytest
from tests.phase2.conftest import make_json_jobs, assert_valid_job, assert_no_duplicates

def run(c): return asyncio.get_event_loop().run_until_complete(c)

PHASE2_SOURCES = {
    "malt", "upwork", "remoteok", "freelancer.com",
    "fiverr", "toptal", "kicklox",
}
ALL_SOURCES = {
    "codeur", "reddit", "welovedevs", "remixjobs",
    "freelance.com", "404works", "comeup", "befreelancr", "collective.work",
} | PHASE2_SOURCES


# ── 1. Enregistrement ─────────────────────────────────────────

class TestSourceRegistrationPhase2:

    def test_all_phase2_in_source_map(self):
        from agents.collector import SOURCE_MAP
        for src in PHASE2_SOURCES:
            assert src in SOURCE_MAP, f"'{src}' manquant dans SOURCE_MAP"

    def test_all_phase2_callable(self):
        from agents.collector import SOURCE_MAP
        for src in PHASE2_SOURCES:
            assert callable(SOURCE_MAP[src]), f"SOURCE_MAP['{src}'] non callable"

    def test_source_map_has_16_sources(self):
        from agents.collector import SOURCE_MAP
        assert len(SOURCE_MAP) >= 16, f"Attendu ≥16 sources, obtenu {len(SOURCE_MAP)}"

    def test_all_phase2_in_settings(self):
        from config.settings import settings
        enabled = set(settings.SOURCES_ENABLED)
        for src in PHASE2_SOURCES:
            assert src in enabled, f"'{src}' absent de SOURCES_ENABLED"


# ── 2. Contrat de chaque source Phase 2 ──────────────────────

class TestSourceContractsPhase2:
    """Vérifie que chaque source retourne bien une liste."""

    SOURCES_TO_TEST = [
        ("sources.upwork",          "get_upwork_jobs",         "upwork"),
        ("sources.remoteok",        "get_remoteok_jobs",       "remoteok"),
        ("sources.freelancer_com",  "get_freelancer_com_jobs", "freelancer.com"),
        ("sources.fiverr",          "get_fiverr_jobs",         "fiverr"),
        ("sources.toptal",          "get_toptal_jobs",         "toptal"),
        ("sources.kicklox",         "get_kicklox_jobs",        "kicklox"),
    ]

    @pytest.mark.parametrize("module,fn,source", SOURCES_TO_TEST)
    def test_returns_list_on_network_error(self, module, fn, source):
        import importlib, requests as r
        mod  = importlib.import_module(module)
        func = getattr(mod, fn)
        with (
            patch_requests(module, side_effect=r.RequestException("down")),
            patch_sleep(module),
        ):
            jobs = run(func())
        assert isinstance(jobs, list), f"[{source}] doit retourner une liste même sur erreur"

    @pytest.mark.parametrize("module,fn,source", SOURCES_TO_TEST)
    def test_never_raises_exception(self, module, fn, source):
        import importlib, requests as r
        mod  = importlib.import_module(module)
        func = getattr(mod, fn)
        with (
            patch_requests(module, side_effect=r.RequestException("boom")),
            patch_sleep(module),
        ):
            try:
                run(func())
            except Exception as exc:
                pytest.fail(f"[{source}] a levé une exception: {exc}")


# ── 3. Collector 16 sources ───────────────────────────────────

class TestCollectorPhase2Integration:

    def _fake(self, n, name):
        jobs = make_json_jobs(n, name)
        async def _fn(): return jobs
        return _fn

    def _crash(self):
        async def _fn(): raise Exception("crash simulé")
        return _fn

    def test_collector_aggregates_16_sources(self):
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

        assert len(jobs) == len(names) * 2, (
            f"Attendu {len(names)*2} jobs, obtenu {len(jobs)}"
        )

    def test_collector_dedup_across_all_sources(self):
        from agents.collector import collect_jobs
        from config.settings import settings
        import agents.collector as col

        shared = "https://example.com/shared"
        dup    = [{"title": "Dup", "description": "", "url": shared,
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

    def test_collector_resilient_3_crashes(self):
        """3 sources crashent → les 13 autres livrent quand même."""
        from agents.collector import collect_jobs
        from config.settings import settings
        import agents.collector as col

        names    = list(ALL_SOURCES)
        fake_map = {n: self._fake(2, n) for n in names}
        crash_names = list(PHASE2_SOURCES)[:3]
        for n in crash_names:
            fake_map[n] = self._crash()

        orig_map, orig_en = col.SOURCE_MAP.copy(), settings.SOURCES_ENABLED[:]
        col.SOURCE_MAP       = fake_map
        settings.SOURCES_ENABLED = names
        try:
            jobs = run(collect_jobs())
        finally:
            col.SOURCE_MAP           = orig_map
            settings.SOURCES_ENABLED = orig_en

        expected = (len(names) - 3) * 2
        assert len(jobs) >= expected, (
            f"Attendu ≥{expected} jobs après 3 crashes, obtenu {len(jobs)}"
        )


# ── Helpers ───────────────────────────────────────────────────

from contextlib import contextmanager
from unittest.mock import patch as _patch

@contextmanager
def patch_requests(module: str, **kwargs):
    with _patch(f"{module}.requests.get", **kwargs):
        yield

@contextmanager
def patch_sleep(module: str):
    with _patch(f"{module}.asyncio.sleep", return_value=None):
        yield
