# =============================================================
# agents/collector.py — agrège toutes les sources
# =============================================================

import asyncio
from config.settings import settings

# ── Sources Phase 0 (base) ───────────────────────────────────
from sources.codeur        import get_codeur_jobs
from sources.reddit        import get_reddit_jobs
from sources.welovedevs    import get_welovedevs_jobs, get_remixjobs_jobs

# ── Sources Phase 1 — plateformes françaises ─────────────────
from sources.freelance_com   import get_freelance_com_jobs
from sources.works404        import get_404works_jobs
from sources.comeup          import get_comeup_jobs
from sources.befreelancr     import get_befreelancr_jobs
from sources.collective_work import get_collective_work_jobs

# ── Sources Phase 2 — FR Playwright + internationales ────────
from sources.malt            import get_malt_jobs
from sources.upwork          import get_upwork_jobs
from sources.remoteok        import get_remoteok_jobs
from sources.freelancer_com  import get_freelancer_com_jobs
from sources.fiverr          import get_fiverr_jobs
from sources.toptal          import get_toptal_jobs
from sources.kicklox         import get_kicklox_jobs

# ── Sources Phase 3 — Réseaux sociaux & communautés ──────────
from sources.hackernews    import get_hackernews_jobs
from sources.devto         import get_devto_jobs
from sources.linkedin      import get_linkedin_jobs
from sources.twitter       import get_twitter_jobs
from sources.indiehackers  import get_indiehackers_jobs

# ── Sources nouvelles ─────────────────────────────────────────
from sources.github_jobs   import get_github_jobs
from sources.rss_custom    import get_custom_rss_jobs


SOURCE_MAP = {
    # Phase 0
    "codeur":           get_codeur_jobs,
    "reddit":           get_reddit_jobs,
    "welovedevs":       get_welovedevs_jobs,
    "remixjobs":        get_remixjobs_jobs,
    # Phase 1
    "freelance.com":    get_freelance_com_jobs,
    "404works":         get_404works_jobs,
    "comeup":           get_comeup_jobs,
    "befreelancr":      get_befreelancr_jobs,
    "collective.work":  get_collective_work_jobs,
    # Phase 2
    "malt":             get_malt_jobs,
    "upwork":           get_upwork_jobs,
    "remoteok":         get_remoteok_jobs,
    "freelancer.com":   get_freelancer_com_jobs,
    "fiverr":           get_fiverr_jobs,
    "toptal":           get_toptal_jobs,
    "kicklox":          get_kicklox_jobs,
    # Phase 3
    "hackernews":       get_hackernews_jobs,
    "dev.to":           get_devto_jobs,
    "linkedin":         get_linkedin_jobs,
    "twitter":          get_twitter_jobs,
    "indiehackers":     get_indiehackers_jobs,
    # Nouvelles sources
    "github.jobs":      get_github_jobs,
    "rss.custom":       get_custom_rss_jobs,
}


async def collect_jobs() -> list:
    """Lance toutes les sources activées en parallèle."""
    print("\n📡 COLLECTOR — Lancement des sources...")

    tasks = []
    for source_name in settings.SOURCES_ENABLED:
        fn = SOURCE_MAP.get(source_name)
        if fn:
            tasks.append(fn())
        else:
            print(f"  ⚠️  Source inconnue : {source_name}")

    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_jobs = []
    for i, res in enumerate(results):
        source = settings.SOURCES_ENABLED[i] if i < len(settings.SOURCES_ENABLED) else "?"
        if isinstance(res, Exception):
            print(f"  ❌ Source '{source}' a échoué: {res}")
        elif isinstance(res, list):
            all_jobs.extend(res)

    # Déduplique par URL dès la collecte
    seen_urls = set()
    unique_jobs = []
    for job in all_jobs:
        url = job.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_jobs.append(job)

    print(f"\n📊 COLLECTOR — {len(unique_jobs)} missions uniques récupérées\n")
    return unique_jobs
