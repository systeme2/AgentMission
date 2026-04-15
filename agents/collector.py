# =============================================================
# agents/collector.py — agrège toutes les sources
# =============================================================

import asyncio
import hashlib
import re
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
from sources.github_jobs       import get_github_jobs
from sources.rss_custom        import get_custom_rss_jobs

# ── Sources FR supplémentaires ────────────────────────────────
from sources.cinq_euros        import get_cinq_euros_jobs
from sources.welcome_jungle    import get_welcome_jungle_jobs
from sources.indeed_fr         import get_indeed_fr_jobs
from sources.leboncoin         import get_leboncoin_jobs
from sources.cremedelacreme    import get_cremedelacreme_jobs

# ── Forums & communautés FR ───────────────────────────────────
from sources.webrankseo        import get_webrankseo_jobs
from sources.hardware_fr       import get_hardware_fr_jobs
from sources.stackoverflow_fr  import get_stackoverflow_fr_jobs
from sources.paruvendu         import get_paruvendu_jobs
from sources.wellfound         import get_wellfound_jobs
from sources.product_hunt      import get_product_hunt_jobs
from sources.facebook_groups   import get_facebook_groups_jobs

# ── Sources Round 3 — FR spécialisées ────────────────────────
from sources.freelancerepublik import get_freelancerepublik_jobs
from sources.france_travail    import get_france_travail_jobs
from sources.sortlist          import get_sortlist_jobs
from sources.graphiste         import get_graphiste_jobs


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
    # Sources FR supplémentaires
    "5euros":           get_cinq_euros_jobs,
    "welcomejungle":    get_welcome_jungle_jobs,
    "indeed.fr":        get_indeed_fr_jobs,
    "leboncoin":        get_leboncoin_jobs,
    "cremedelacreme":   get_cremedelacreme_jobs,
    # Forums & communautés FR
    "webrankseo":       get_webrankseo_jobs,
    "hardware.fr":      get_hardware_fr_jobs,
    "stackoverflow.fr": get_stackoverflow_fr_jobs,
    "paruvendu":        get_paruvendu_jobs,
    "wellfound":        get_wellfound_jobs,
    "producthunt":      get_product_hunt_jobs,
    # Réseaux sociaux (auth requise)
    "facebook.groups":  get_facebook_groups_jobs,
    # Communautés EN (déjà présentes)
    "indiehackers":     get_indiehackers_jobs,
    # Round 3 — FR spécialisées
    "freelancerepublik": get_freelancerepublik_jobs,
    "france-travail":    get_france_travail_jobs,
    "sortlist":          get_sortlist_jobs,
    "graphiste":         get_graphiste_jobs,
}


async def collect_jobs() -> list:
    """Lance toutes les sources activées en parallèle."""
    print("\n📡 COLLECTOR — Lancement des sources...")

    task_sources = []
    tasks = []
    for source_name in settings.SOURCES_ENABLED:
        fn = SOURCE_MAP.get(source_name)
        if fn:
            task_sources.append(source_name)
            tasks.append(fn())
        else:
            print(f"  ⚠️  Source inconnue : {source_name}")

    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_jobs = []
    for i, res in enumerate(results):
        source = task_sources[i] if i < len(task_sources) else "?"
        if isinstance(res, Exception):
            print(f"  ❌ Source '{source}' a échoué: {res}")
        elif isinstance(res, list):
            for job in res:
                if not isinstance(job, dict):
                    continue
                normalized = _normalize_job(job, fallback_source=source)
                if normalized:
                    all_jobs.append(normalized)

    # ── Dédup 1 : URL canonique quand dispo, sinon fingerprint ───────────
    seen_keys = set()
    deduped_jobs = []
    for job in all_jobs:
        dedup_key = _dedup_key(job)
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)
        deduped_jobs.append(job)

    # ── Dédup 2 : hash technique pour la DB (sans suppression) ─────────
    # Le hash est conservé pour la persistance.
    hash_deduped = []
    for job in deduped_jobs:
        h = _title_hash(job.get("title", ""), job.get("source", ""))
        job["title_hash"] = h
        hash_deduped.append(job)

    removed = len(all_jobs) - len(hash_deduped)
    print(f"\n📊 COLLECTOR — {len(hash_deduped)} missions uniques "
          f"({removed} doublons supprimés)\n")
    return hash_deduped


def _title_hash(title: str, source: str) -> str:
    """Hash MD5 court du titre normalisé + source pour détecter les doublons cross-URL."""
    normalized = re.sub(r"\W+", " ", title.lower()).strip()
    return hashlib.md5(f"{normalized}|{source}".encode()).hexdigest()[:12]


def _normalize_job(job: dict, fallback_source: str) -> dict | None:
    """Nettoie un job brut pour éviter les entrées inexploitables."""
    title = str(job.get("title", "")).strip()
    description = str(job.get("description", "")).strip()
    url = _canonical_url(str(job.get("url", "")).strip())
    if not title and not description and not url:
        return None

    normalized = dict(job)
    normalized["title"] = title or "Mission sans titre"
    normalized["description"] = description
    normalized["source"] = str(job.get("source") or fallback_source or "").strip()
    normalized["url"] = url
    return normalized


def _canonical_url(url: str) -> str:
    """Normalise une URL pour une déduplication plus stable."""
    if not url:
        return ""
    return re.sub(r"(#.*)$", "", url).strip()


def _dedup_key(job: dict) -> str:
    """
    Clé de déduplication robuste:
    - URL canonique si présente (cas principal)
    - sinon empreinte sur source+titre+description (évite perte des jobs sans URL)
    """
    url = job.get("url", "")
    if url:
        return f"url:{url}"

    title = re.sub(r"\W+", " ", (job.get("title") or "").lower()).strip()
    description = re.sub(r"\W+", " ", (job.get("description") or "").lower()).strip()
    source = (job.get("source") or "").lower().strip()
    fingerprint = hashlib.md5(f"{source}|{title}|{description[:200]}".encode()).hexdigest()
    return f"fp:{fingerprint}"
