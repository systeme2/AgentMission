# =============================================================
# sources/welcome_jungle.py — scraper Welcome to the Jungle
# =============================================================
#
# Welcome to the Jungle est un job board FR très populaire.
# Il expose une API publique JSON pour la recherche d'offres.
#
# On filtre sur : "freelance" ou "CDD" (souvent transformable)
# dans les catégories tech/web/développement.
# =============================================================

import asyncio
import requests
from config.settings import settings
from sources.utils import async_fetch

BASE_URL   = "https://www.welcometothejungle.com"
# API de recherche publique (non authentifiée, pagination JSON)
API_URL    = "https://api.welcometothejungle.com/api/v1/jobs"
HEADERS    = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
    "Accept":          "application/json",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Referer":         BASE_URL,
}

_SEARCH_QUERIES = [
    {"query": "développeur freelance", "contract_type": "freelance"},
    {"query": "wordpress freelance",   "contract_type": "freelance"},
    {"query": "développeur web",       "contract_type": "temporary"},
]


async def get_welcome_jungle_jobs() -> list:
    print("🕷️  [WelcomeJungle] Scraping en cours...")
    jobs: list = []
    seen_urls: set = set()

    # Tentative API JSON
    for q in _SEARCH_QUERIES[:1]:
        try:
            params = {
                "query":     q["query"],
                "page":      1,
                "per_page":  20,
                "country_code": "FR",
            }
            resp = await async_fetch(API_URL, headers=HEADERS, params=params, timeout=20)

            if resp.status_code == 200 and "application/json" in resp.headers.get("Content-Type", ""):
                data = resp.json()
                offers = data.get("jobs", data.get("results", data if isinstance(data, list) else []))

                for offer in offers[:20]:
                    if not isinstance(offer, dict):
                        continue
                    title   = (offer.get("name") or offer.get("title") or "").strip()
                    company = (offer.get("organization", {}) or {}).get("name", "") if isinstance(offer.get("organization"), dict) else ""
                    slug    = offer.get("slug") or offer.get("reference") or offer.get("id", "")
                    url     = f"{BASE_URL}/fr/companies/-/jobs/{slug}" if slug else ""
                    desc    = (offer.get("description") or offer.get("summary") or "")[:500]

                    if not title or not url or url in seen_urls:
                        continue
                    seen_urls.add(url)

                    full_title = f"{title} @ {company}".strip(" @") if company else title
                    jobs.append({
                        "title":       full_title,
                        "description": desc,
                        "url":         url,
                        "budget_raw":  "",
                        "source":      "welcomejungle",
                    })

        except Exception as exc:
            print(f"  ⚠️  [WelcomeJungle] API: {exc}")

        await asyncio.sleep(settings.REQUEST_DELAY)

    print(f"  ✅ [WelcomeJungle] {len(jobs)} missions trouvées")
    return jobs
