# =============================================================
# tests/phase4/test_load_concurrent.py
# =============================================================
#
# Tests de charge et de concurrence :
#   - 21 sources lancées en parallèle sans deadlock
#   - Pas de race condition sur la DB
#   - Déduplication sous charge
#   - Temps d'exécution acceptable
# =============================================================

import asyncio, pytest, time
from unittest.mock import patch
from tests.phase4.conftest import make_raw_job, make_analyzed_job, run


def _fake_source(n, name, delay=0.0):
    """Source async avec délai simulé (pour tester la concurrence)."""
    jobs = [make_raw_job(i, name) for i in range(1, n + 1)]
    async def _fn():
        if delay:
            await asyncio.sleep(delay)
        return jobs
    return _fn


def _crash_source():
    async def _fn():
        raise RuntimeError("source crash")
    return _fn


def _slow_source(n, name, delay=0.1):
    return _fake_source(n, name, delay)


ALL_21_SOURCES = [
    "codeur", "reddit", "remixjobs", "welovedevs",
    "freelance.com", "404works", "comeup", "befreelancr", "collective.work",
    "malt", "upwork", "remoteok", "freelancer.com", "fiverr", "toptal", "kicklox",
    "hackernews", "dev.to", "linkedin", "twitter", "indiehackers",
]


class TestConcurrentCollector:

    def _run_collector(self, fake_map, sources):
        import agents.collector as col_mod
        from config.settings import settings
        orig_map = col_mod.SOURCE_MAP.copy()
        orig_en  = settings.SOURCES_ENABLED[:]
        col_mod.SOURCE_MAP       = fake_map
        settings.SOURCES_ENABLED = sources
        try:
            from agents.collector import collect_jobs
            return run(collect_jobs())
        finally:
            col_mod.SOURCE_MAP       = orig_map
            settings.SOURCES_ENABLED = orig_en

    def test_all_21_sources_parallel_no_deadlock(self):
        """21 sources en parallèle → pas de deadlock, résultat en < 5s."""
        fake_map = {s: _fake_source(3, s) for s in ALL_21_SOURCES}
        start = time.time()
        jobs  = self._run_collector(fake_map, ALL_21_SOURCES)
        elapsed = time.time() - start

        assert isinstance(jobs, list)
        assert len(jobs) == 21 * 3        # 21 sources × 3 jobs
        assert elapsed < 5.0, f"Trop lent: {elapsed:.2f}s"

    def test_all_21_sources_with_random_crashes(self):
        """Même si 7 sources crashent, les 14 autres livrent."""
        crash_sources = ALL_21_SOURCES[:7]
        ok_sources    = ALL_21_SOURCES[7:]

        fake_map = {s: _crash_source()       for s in crash_sources}
        fake_map.update({s: _fake_source(2, s) for s in ok_sources})

        jobs = self._run_collector(fake_map, ALL_21_SOURCES)
        assert len(jobs) == len(ok_sources) * 2

    def test_deduplication_under_load(self):
        """Même URL renvoyée par toutes les sources → 1 seul job."""
        shared_url = "https://example.com/shared"
        def make_dup_source(name):
            job = make_raw_job(1, name)
            job["url"] = shared_url
            async def _fn(): return [job]
            return _fn

        fake_map = {s: make_dup_source(s) for s in ALL_21_SOURCES}
        jobs     = self._run_collector(fake_map, ALL_21_SOURCES)
        urls     = [j["url"] for j in jobs]
        assert urls.count(shared_url) == 1

    def test_slow_sources_dont_block_fast_ones(self):
        """Une source lente (0.2s) ne bloque pas les sources rapides."""
        fake_map = {s: _fake_source(2, s) for s in ALL_21_SOURCES}
        # Rend 3 sources lentes
        for s in ALL_21_SOURCES[:3]:
            fake_map[s] = _slow_source(2, s, delay=0.2)

        start   = time.time()
        jobs    = self._run_collector(fake_map, ALL_21_SOURCES)
        elapsed = time.time() - start

        assert len(jobs) == 21 * 2
        # Avec asyncio gather, le total ≈ max(delays) ≈ 0.2s, pas la somme
        assert elapsed < 3.0, f"Sources parallèles trop lentes: {elapsed:.2f}s"

    def test_empty_sources_dont_affect_others(self):
        """Sources retournant [] n'affectent pas le total des autres."""
        fake_map = {s: _fake_source(0, s) for s in ALL_21_SOURCES[:10]}
        fake_map.update({s: _fake_source(3, s) for s in ALL_21_SOURCES[10:]})
        jobs = self._run_collector(fake_map, ALL_21_SOURCES)
        assert len(jobs) == 11 * 3   # 11 sources avec 3 jobs chacune


class TestDatabaseConcurrency:

    def test_concurrent_saves_no_duplicate(self, tmp_path):
        """Plusieurs coroutines sauvegardent des jobs en même temps → pas de doublon."""
        import core.database as db_mod
        original = db_mod.settings.DB_PATH
        db_mod.settings.DB_PATH = str(tmp_path / "concurrent.db")
        db_mod.init_db()

        async def save_batch(batch):
            for job in batch:
                db_mod.save_mission(job)

        batches = [
            [make_analyzed_job(i, f"src_{batch}") for i in range(5)]
            for batch in range(4)
        ]

        async def run_all():
            await asyncio.gather(*[save_batch(b) for b in batches])

        asyncio.get_event_loop().run_until_complete(run_all())
        stats = db_mod.get_stats()
        assert stats["total"] == 20  # 4 batches × 5 jobs

        db_mod.settings.DB_PATH = original

    def test_concurrent_same_url_saves_once(self, tmp_path):
        """Deux coroutines tentant de sauvegarder le même URL → 1 seule ligne."""
        import core.database as db_mod
        original = db_mod.settings.DB_PATH
        db_mod.settings.DB_PATH = str(tmp_path / "race.db")
        db_mod.init_db()

        same_job = make_analyzed_job(1, "codeur", 0.8)

        async def save_same():
            db_mod.save_mission(dict(same_job))

        async def run_all():
            await asyncio.gather(save_same(), save_same(), save_same())

        asyncio.get_event_loop().run_until_complete(run_all())
        all_missions = db_mod.get_all_missions()
        urls = [m["url"] for m in all_missions]
        assert urls.count(same_job["url"]) == 1

        db_mod.settings.DB_PATH = original


class TestCollectorPerformance:

    def test_100_jobs_processed_fast(self):
        """100 jobs dans le collector doivent être traités en < 1s."""
        import agents.collector as col_mod
        from config.settings import settings

        big_source = _fake_source(100, "big")
        orig_map = col_mod.SOURCE_MAP.copy()
        orig_en  = settings.SOURCES_ENABLED[:]
        col_mod.SOURCE_MAP       = {"big": big_source}
        settings.SOURCES_ENABLED = ["big"]

        start = time.time()
        try:
            from agents.collector import collect_jobs
            jobs = run(collect_jobs())
        finally:
            col_mod.SOURCE_MAP       = orig_map
            settings.SOURCES_ENABLED = orig_en

        elapsed = time.time() - start
        assert len(jobs) == 100
        assert elapsed < 1.0, f"100 jobs trop lents: {elapsed:.2f}s"

    def test_dedup_1000_jobs_same_url(self):
        """1000 jobs avec la même URL → 1 seul après dédup."""
        import agents.collector as col_mod
        from config.settings import settings

        shared = "https://shared.com/job"
        async def dup_source():
            return [{"title": f"Job {i}", "description": "", "url": shared,
                     "budget_raw": "", "source": "dup"} for i in range(1000)]

        orig_map = col_mod.SOURCE_MAP.copy()
        orig_en  = settings.SOURCES_ENABLED[:]
        col_mod.SOURCE_MAP       = {"dup": dup_source}
        settings.SOURCES_ENABLED = ["dup"]
        try:
            from agents.collector import collect_jobs
            jobs = run(collect_jobs())
        finally:
            col_mod.SOURCE_MAP       = orig_map
            settings.SOURCES_ENABLED = orig_en

        assert len(jobs) == 1
