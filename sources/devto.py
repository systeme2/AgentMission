# =============================================================
# sources/devto.py — scraper Dev.to via API REST publique
# =============================================================
#
# Dev.to expose une API REST complète et publique (sans auth
# pour la lecture). On cible les articles avec les tags :
#   #hiring  #jobs  #career  #webdev  #javascript  #react
#
# Endpoint principal :
#   GET https://dev.to/api/articles?tag=hiring&per_page=30
#
# Chaque article peut être une offre d'emploi, un thread
# "freelancer available" ou une annonce de mission.
# On filtre pour ne garder que les offres de type "hiring".
# =============================================================

import asyncio
import requests
from config.settings import settings

API_BASE = "https://dev.to/api"
HEADERS  = {
    "User-Agent": "MissionAgentBot/1.0 (personal freelance tracker)",
    "Accept":     "application/json",
}

# Tags à requêter — chacun donne une liste d'articles
_TAGS = ["hiring", "jobs", "joboffer", "freelance"]

# Mots-clés dans le titre pour filtrer les vraies offres
_HIRING_KEYWORDS = [
    "hiring", "looking for", "we need", "job", "position",
    "developer", "engineer", "remote", "freelance", "opportunity",
    "opening", "available",
]

_NEGATIVE_KEYWORDS = [
    "i am looking", "looking for work", "available for hire",
    "seeking", "i'm a", "portfolio",
]


def _is_job_offer(article: dict) -> bool:
    """Retourne True si l'article ressemble à une offre d'emploi."""
    title = (article.get("title") or "").lower()
    tags  = [t.get("name", "").lower() for t in (article.get("tags") or [])]

    # Exclusion si c'est un freelance cherchant du travail (pas une offre)
    if any(neg in title for neg in _NEGATIVE_KEYWORDS):
        return False

    # Inclusion si tag hiring direct
    if any(t in ("hiring", "job", "jobs", "joboffer") for t in tags):
        return True

    # Inclusion si titre contient mots-clés d'offre
    return any(kw in title for kw in _HIRING_KEYWORDS)


def _fetch_tag(tag: str, per_page: int = 20) -> list:
    """Récupère les articles récents pour un tag donné."""
    jobs = []
    try:
        resp = requests.get(
            f"{API_BASE}/articles",
            params={"tag": tag, "per_page": per_page, "state": "fresh"},
            headers=HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        articles = resp.json()

        for article in articles:
            if not _is_job_offer(article):
                continue

            art_id    = article.get("id", "")
            slug      = article.get("slug", "")
            username  = (article.get("user") or {}).get("username", "")
            url       = article.get("url") or f"https://dev.to/{username}/{slug}"

            title     = (article.get("title") or "").strip()
            desc      = (article.get("description") or "").strip()[:500]
            pub_date  = article.get("published_at", "")

            if title and url:
                jobs.append({
                    "title":       title,
                    "description": desc,
                    "url":         url,
                    "budget_raw":  "",
                    "source":      "dev.to",
                    "date":        pub_date,
                })

    except requests.RequestException as exc:
        print(f"  ⚠️  [Dev.to] réseau tag={tag}: {exc}")
    except (ValueError, KeyError) as exc:
        print(f"  ⚠️  [Dev.to] parsing tag={tag}: {exc}")

    return jobs


async def get_devto_jobs() -> list:
    print("🕷️  [Dev.to] Scraping API en cours...")

    all_jobs:  list = []
    seen_urls: set  = set()

    for tag in _TAGS:
        try:
            batch = await asyncio.to_thread(_fetch_tag, tag)
        except Exception as exc:
            print(f"  ⚠️  [Dev.to] to_thread tag={tag}: {exc}")
            batch = []
        for job in batch:
            if job["url"] not in seen_urls:
                seen_urls.add(job["url"])
                all_jobs.append(job)
        await asyncio.sleep(settings.REQUEST_DELAY)

    print(f"  ✅ [Dev.to] {len(all_jobs)} missions trouvées")
    return all_jobs
