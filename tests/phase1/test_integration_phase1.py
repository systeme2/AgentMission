# =============================================================
# tests/phase1/test_integration_phase1.py
# =============================================================
#
# Tests d'intégration : vérifie que toutes les sources Phase 1
# sont correctement enregistrées dans le collector et que le
# pipeline complet fonctionne avec des mocks réseau.
# =============================================================

import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from tests.phase1.conftest import (
    make_html, make_json_jobs,
    assert_valid_job, assert_no_duplicates,
)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── Constantes ────────────────────────────────────────────────

PHASE1_SOURCES = {
    "freelance.com",
    "404works",
    "comeup",
    "befreelancr",
    "collective.work",
}

ALL_SOURCES = {
    "codeur", "reddit", "welovedevs", "remixjobs",
} | PHASE1_SOURCES


# ── 1. Enregistrement dans SOURCE_MAP ─────────────────────────

class TestSourceRegistration:

    def test_all_phase1_sources_in_source_map(self):
        from agents.collector import SOURCE_MAP
        for source in PHASE1_SOURCES:
            assert source in SOURCE_MAP, (
                f"Source '{source}' manquante dans SOURCE_MAP"
            )

    def test_all_phase1_sources_callable(self):
        from agents.collector import SOURCE_MAP
        for source in PHASE1_SOURCES:
            fn = SOURCE_MAP.get(source)
            assert callable(fn), f"SOURCE_MAP['{source}'] n'est pas callable"

    def test_source_map_has_9_sources(self):
        from agents.collector import SOURCE_MAP
        assert len(SOURCE_MAP) >= 9, (
            f"Attendu ≥9 sources, obtenu {len(SOURCE_MAP)}: {list(SOURCE_MAP.keys())}"
        )

    def test_all_phase1_sources_in_settings(self):
        from config.settings import settings
        enabled = set(settings.SOURCES_ENABLED)
        for source in PHASE1_SOURCES:
            assert source in enabled, (
                f"Source '{source}' absente de SOURCES_ENABLED"
            )


# ── 2. Contrat de chaque source ───────────────────────────────

class TestSourceContracts:
    """Vérifie que chaque source Phase 1 respecte le contrat : liste de dicts."""

    def _run_source_with_mock(self, source_module, fn_name, html_or_data):
        """Lance une source avec le réseau mocké."""
        import importlib
        mod = importlib.import_module(source_module)
        fn  = getattr(mod, fn_name)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text        = html_or_data if isinstance(html_or_data, str) else ""
        mock_resp.headers     = {"Content-Type": "text/html"}
        mock_resp.raise_for_status = MagicMock()

        with patch(f"{source_module}.requests.get", return_value=mock_resp), \
             patch(f"{source_module}.asyncio.sleep", return_value=None):
            return run(fn())

    def test_freelance_com_contract(self):
        html = make_html(
            [{"title": "Dev PHP Laravel senior", "url": "/missions/1"}],
            "project"
        )
        jobs = self._run_source_with_mock("sources.freelance_com", "get_freelance_com_jobs", html)
        assert isinstance(jobs, list)

    def test_works404_contract(self):
        html = make_html(
            [{"title": "UX Designer freelance", "url": "/jobs/1"}],
            "job-item"
        )
        jobs = self._run_source_with_mock("sources.works404", "get_404works_jobs", html)
        assert isinstance(jobs, list)

    def test_comeup_contract(self):
        html = make_html(
            [{"title": "Expert SEO Paris", "url": "/fr/services/1"}],
            "service-card"
        )
        jobs = self._run_source_with_mock("sources.comeup", "get_comeup_jobs", html)
        assert isinstance(jobs, list)

    def test_befreelancr_contract(self):
        html = make_html(
            [{"title": "Développeur React", "url": "/missions/1"}],
            "mission-card"
        )
        jobs = self._run_source_with_mock("sources.befreelancr", "get_befreelancr_jobs", html)
        assert isinstance(jobs, list)

    def test_collective_work_contract(self):
        html = make_html(
            [{"title": "Lead Dev TypeScript", "url": "/jobs/1"}],
            "job-card"
        )
        jobs = self._run_source_with_mock("sources.collective_work", "get_collective_work_jobs", html)
        assert isinstance(jobs, list)


# ── 3. Collector agrège toutes les sources ────────────────────

class TestCollectorIntegration:
    """
    Ces tests patchent directement SOURCE_MAP dans agents.collector
    pour éviter tout appel réseau réel, quelle que soit la source.
    """

    def _fake_source(self, n: int, name: str):
        """Retourne une coroutine async produisant n faux jobs."""
        jobs = make_json_jobs(n, name)
        async def _fn():
            return jobs
        return _fn

    def _fake_source_crash(self):
        """Retourne une coroutine async qui lève une exception."""
        async def _fn():
            raise Exception("source crash simulé")
        return _fn

    def test_collector_aggregates_all_sources(self):
        from agents.collector import collect_jobs
        from config.settings import settings
        import agents.collector as col_mod

        source_names = [
            "codeur", "reddit", "welovedevs", "remixjobs",
            "freelance.com", "404works", "comeup", "befreelancr", "collective.work",
        ]
        fake_map = {name: self._fake_source(2, name) for name in source_names}

        original_map     = col_mod.SOURCE_MAP.copy()
        original_enabled = settings.SOURCES_ENABLED[:]
        col_mod.SOURCE_MAP       = fake_map
        settings.SOURCES_ENABLED = source_names
        try:
            jobs = run(collect_jobs())
        finally:
            col_mod.SOURCE_MAP       = original_map
            settings.SOURCES_ENABLED = original_enabled

        assert isinstance(jobs, list)
        assert len(jobs) == 18, f"Attendu 18 jobs (9×2), obtenu {len(jobs)}"

    def test_collector_deduplicates_across_sources(self):
        """Si deux sources retournent la même URL, une seule doit être gardée."""
        from agents.collector import collect_jobs
        from config.settings import settings
        import agents.collector as col_mod

        shared_url = "https://example.com/shared-mission"
        dup_job    = [{"title": "Mission en double", "description": "",
                       "url": shared_url, "budget_raw": "", "source": "test"}]

        source_names = [
            "codeur", "reddit", "freelance.com", "404works",
            "comeup", "befreelancr", "collective.work", "welovedevs", "remixjobs",
        ]

        async def _dup():
            return dup_job

        fake_map = {name: _dup for name in source_names}

        original_map     = col_mod.SOURCE_MAP.copy()
        original_enabled = settings.SOURCES_ENABLED[:]
        col_mod.SOURCE_MAP       = fake_map
        settings.SOURCES_ENABLED = source_names
        try:
            jobs = run(collect_jobs())
        finally:
            col_mod.SOURCE_MAP       = original_map
            settings.SOURCES_ENABLED = original_enabled

        urls = [j["url"] for j in jobs]
        assert urls.count(shared_url) == 1, (
            f"URL dupliquée non supprimée : {urls.count(shared_url)} occurrences"
        )

    def test_collector_resilient_to_source_failure(self):
        """Si une source plante, les autres doivent quand même retourner leurs jobs."""
        from agents.collector import collect_jobs
        from config.settings import settings
        import agents.collector as col_mod

        source_names = [
            "codeur", "reddit", "freelance.com", "404works",
            "comeup", "befreelancr", "collective.work", "welovedevs", "remixjobs",
        ]
        fake_map = {name: self._fake_source(2, name) for name in source_names}
        # freelance.com plante
        fake_map["freelance.com"] = self._fake_source_crash()

        original_map     = col_mod.SOURCE_MAP.copy()
        original_enabled = settings.SOURCES_ENABLED[:]
        col_mod.SOURCE_MAP       = fake_map
        settings.SOURCES_ENABLED = source_names
        try:
            jobs = run(collect_jobs())
        finally:
            col_mod.SOURCE_MAP       = original_map
            settings.SOURCES_ENABLED = original_enabled

        # freelance.com plante → 8 sources × 2 = 16 jobs attendus
        assert len(jobs) >= 14, (
            f"Trop peu de jobs après crash d'une source: {len(jobs)}"
        )


# ── 4. Propriétés universelles des jobs ──────────────────────

class TestUniversalJobProperties:
    """Chaque job produit par n'importe quelle source doit respecter ces règles."""

    SOURCES_AND_FUNCTIONS = [
        ("sources.freelance_com",   "get_freelance_com_jobs",   "freelance.com",   "project"),
        ("sources.works404",        "get_404works_jobs",        "404works",        "job-item"),
        ("sources.comeup",          "get_comeup_jobs",          "comeup",          "service-card"),
        ("sources.befreelancr",     "get_befreelancr_jobs",     "befreelancr",     "mission-card"),
        ("sources.collective_work", "get_collective_work_jobs", "collective.work", "job-card"),
    ]

    @pytest.mark.parametrize("module,fn,source,cls", SOURCES_AND_FUNCTIONS)
    def test_url_starts_with_https(self, module, fn, source, cls):
        import importlib
        mod = importlib.import_module(module)
        func = getattr(mod, fn)
        html = make_html([{"title": f"Test {source}", "url": f"/test/1"}], cls)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = html
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.raise_for_status = MagicMock()

        with patch(f"{module}.requests.get", return_value=mock_resp), \
             patch(f"{module}.asyncio.sleep", return_value=None):
            jobs = run(func())

        for job in jobs:
            assert job["url"].startswith("http"), (
                f"[{source}] URL non absolue: {job['url']}"
            )

    @pytest.mark.parametrize("module,fn,source,cls", SOURCES_AND_FUNCTIONS)
    def test_source_field_matches_expected(self, module, fn, source, cls):
        import importlib
        mod = importlib.import_module(module)
        func = getattr(mod, fn)
        html = make_html([{"title": f"Job test {source}", "url": f"/test/1"}], cls)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = html
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.raise_for_status = MagicMock()

        with patch(f"{module}.requests.get", return_value=mock_resp), \
             patch(f"{module}.asyncio.sleep", return_value=None):
            jobs = run(func())

        for job in jobs:
            assert job["source"] == source, (
                f"Mauvais source: attendu '{source}', obtenu '{job['source']}'"
            )

    @pytest.mark.parametrize("module,fn,source,cls", SOURCES_AND_FUNCTIONS)
    def test_network_failure_never_raises(self, module, fn, source, cls):
        """Aucune source ne doit lever d'exception en cas d'erreur réseau."""
        import importlib, requests as r
        mod = importlib.import_module(module)
        func = getattr(mod, fn)

        with patch(f"{module}.requests.get", side_effect=r.RequestException("network down")), \
             patch(f"{module}.asyncio.sleep", return_value=None):
            try:
                jobs = run(func())
                assert isinstance(jobs, list)
            except Exception as exc:
                pytest.fail(f"[{source}] a levé une exception sur erreur réseau: {exc}")
