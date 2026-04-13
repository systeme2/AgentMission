# =============================================================
# sources/freelancer_com.py — Freelancer.com API publique v1
# =============================================================
#
# Freelancer expose une API REST publique (sans auth pour les
# endpoints de recherche de projets en lecture seule).
#
# Endpoint utilisé :
#   GET https://www.freelancer.com/api/projects/0.1/projects/active/
#
# Docs : https://developers.freelancer.com/docs
#
# Paramètres utiles :
#   query        → mots-clés
#   job_details  → inclut les détails du job
#   full_description → description complète
#   limit        → max 50
# =============================================================

import asyncio
import requests
from config.settings import settings

API_BASE = "https://www.freelancer.com/api/projects/0.1"
HEADERS  = {
    "User-Agent":  "MissionAgentBot/1.0",
    "Accept":      "application/json",
    "Freelancer-OAuth-V1": "",   # non requis pour lecture publique
}

# Requêtes thématiques à lancer
_SEARCH_QUERIES = [
    "wordpress website",
    "react developer",
    "web developer freelance",
    "seo specialist",
    "frontend developer nextjs",
]


def _fetch_projects(query: str, limit: int = 20) -> list:
    """Requête l'API Freelancer pour une query donnée."""
    jobs = []
    url  = f"{API_BASE}/projects/active/"
    params = {
        "query":            query,
        "job_details":      True,
        "full_description": True,
        "limit":            limit,
        "offset":           0,
        "sort_field":       "time_updated",
        "sort_order":       "desc",
    }

    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        result   = data.get("result", {})
        projects = result.get("projects", [])

        for proj in projects:
            pid   = proj.get("id", "")
            seo   = proj.get("seo_url") or ""
            link  = (
                f"https://www.freelancer.com/projects/{seo}"
                if seo else
                f"https://www.freelancer.com/contest/{pid}"
            )

            title = (proj.get("title") or "").strip()
            if not title:
                continue

            desc  = (proj.get("description") or "").strip()[:500]

            # Budget
            budget_obj = proj.get("budget") or {}
            b_min = budget_obj.get("minimum")
            b_max = budget_obj.get("maximum")
            curr  = (proj.get("currency") or {}).get("sign", "$")
            if b_min and b_max:
                budget_str = f"{curr}{b_min} – {curr}{b_max}"
            elif b_min:
                budget_str = f"{curr}{b_min}+"
            else:
                budget_str = ""

            # Pays / langue (optionnel, pour filtrage scorer)
            country = (proj.get("language") or "")

            jobs.append({
                "title":       title,
                "description": desc,
                "url":         link,
                "budget_raw":  budget_str,
                "source":      "freelancer.com",
                "country":     country,
            })

    except requests.RequestException as exc:
        print(f"  ⚠️  [Freelancer.com] réseau pour '{query}': {exc}")
    except (KeyError, ValueError) as exc:
        print(f"  ⚠️  [Freelancer.com] parsing pour '{query}': {exc}")

    return jobs


async def get_freelancer_com_jobs() -> list:
    print("🕷️  [Freelancer.com] Scraping API en cours...")

    all_jobs:  list = []
    seen_urls: set  = set()

    for query in _SEARCH_QUERIES:
        batch = await asyncio.to_thread(_fetch_projects, query)
        for job in batch:
            if job["url"] not in seen_urls:
                seen_urls.add(job["url"])
                all_jobs.append(job)
        await asyncio.sleep(settings.REQUEST_DELAY)

    print(f"  ✅ [Freelancer.com] {len(all_jobs)} missions trouvées")
    return all_jobs
