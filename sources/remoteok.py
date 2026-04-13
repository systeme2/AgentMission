# =============================================================
# sources/remoteok.py — scraper Remote OK (API JSON publique)
# =============================================================
#
# Remote OK expose une API JSON publique non authentifiée :
#   GET https://remoteok.com/api
#
# Retourne ~100 offres récentes, triées par date desc.
# Chaque offre a : id, slug, company, position, tags, date,
#                  description, salary_min, salary_max, url
#
# Contrainte officielle : User-Agent != "null" et 1 req/min max.
# =============================================================

import asyncio
import requests
from config.settings import settings

API_URL = "https://remoteok.com/api"
HEADERS = {
    "User-Agent":      "MissionAgentBot/1.0 (personal freelance tracker)",
    "Accept":          "application/json",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

# Tags tech → on filtre sur ceux-ci pour ne garder que le dev web
_RELEVANT_TAGS = {
    "javascript", "typescript", "react", "vue", "angular", "nextjs",
    "nodejs", "python", "django", "fastapi", "php", "laravel",
    "wordpress", "webdev", "frontend", "backend", "fullstack",
    "css", "html", "ux", "ui", "seo", "shopify", "woocommerce",
    "dev", "developer", "web", "remote",
}


def _is_relevant(job: dict) -> bool:
    """Retourne True si l'offre correspond à du dev web / freelance."""
    tags = {t.lower() for t in (job.get("tags") or [])}
    pos  = (job.get("position") or "").lower()
    return bool(tags & _RELEVANT_TAGS) or any(t in pos for t in _RELEVANT_TAGS)


def _format_salary(job: dict) -> str:
    lo = job.get("salary_min")
    hi = job.get("salary_max")
    if lo and hi:
        return f"${lo} – ${hi}"
    if lo:
        return f"${lo}+"
    return ""


async def get_remoteok_jobs() -> list:
    print("🕷️  [Remote OK] Scraping API en cours...")
    jobs = []

    try:
        resp = await asyncio.to_thread(
            lambda: requests.get(API_URL, headers=HEADERS, timeout=20)
        )
        resp.raise_for_status()
        data = resp.json()

        # Le premier élément est toujours un objet méta {"legal": "..."}
        items = [d for d in data if isinstance(d, dict) and "position" in d]

        for item in items:
            if not _is_relevant(item):
                continue

            position = (item.get("position") or "").strip()
            company  = (item.get("company")  or "").strip()
            title    = f"{position} @ {company}".strip(" @") if company else position

            slug = item.get("slug") or item.get("id") or ""
            url  = item.get("url") or f"https://remoteok.com/remote-jobs/{slug}"
            if not url.startswith("http"):
                url = "https://remoteok.com" + url

            desc = (item.get("description") or "")
            # Supprimer les balises HTML basiques
            import re
            desc = re.sub(r"<[^>]+>", " ", desc)
            desc = re.sub(r"\s+", " ", desc).strip()[:500]

            tags   = ", ".join(item.get("tags") or [])
            salary = _format_salary(item)
            date   = item.get("date", "")

            if title and url:
                jobs.append({
                    "title":       title,
                    "description": desc or tags,
                    "url":         url,
                    "budget_raw":  salary,
                    "source":      "remoteok",
                    "date":        date,
                })

        await asyncio.sleep(settings.REQUEST_DELAY)

    except Exception as exc:
        print(f"  ❌ [Remote OK] {exc}")

    print(f"  ✅ [Remote OK] {len(jobs)} missions trouvées")
    return jobs
