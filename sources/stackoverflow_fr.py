# =============================================================
# sources/stackoverflow_fr.py — Stack Overflow / Stack Exchange
# =============================================================
#
# Stack Exchange expose une API publique JSON (v2.3) sans auth
# (limite : 300 req/jour sans clé, 10 000 avec clé API).
#
# Stratégie : chercher des questions récentes où des gens
# décrivent un besoin de développement et offrent une rémunération.
#
# Tags utiles :
#   - [freelance] [hiring] [job] sur SO
#   - Questions récentes avec mots-clés "cherche développeur"
#
# Note : le job board Stack Overflow a fermé en 2022.
# On scrute donc les questions et le meta-forum.
# =============================================================

import asyncio
import requests
from config.settings import settings
from sources.utils import async_fetch

BASE_URL = "https://api.stackexchange.com/2.3"
HEADERS  = {
    "User-Agent": "MissionAgentBot/1.0 (personal freelance tracker)",
    "Accept":     "application/json",
}

# Requêtes API Stack Exchange
_SEARCHES = [
    # Questions récentes avec tags emploi/freelance
    {
        "site":   "stackoverflow",
        "tagged": "freelance",
        "order":  "desc",
        "sort":   "creation",
    },
    {
        "site":   "stackoverflow",
        "intitle": "cherche développeur",
        "order":   "desc",
        "sort":    "creation",
    },
    {
        "site":    "meta.stackoverflow.com",
        "tagged":  "jobs",
        "order":   "desc",
        "sort":    "creation",
    },
]

# Mots-clés dans le titre qui indiquent une vraie offre
_OFFER_KEYWORDS = [
    "cherche", "recherche", "besoin", "hiring", "looking for",
    "freelance", "developer wanted", "mission", "job offer",
    "remote", "paid", "rémunéré", "rémunération", "budget",
]


def _is_offer(title: str, tags: list) -> bool:
    low  = title.lower()
    has_offer_kw = any(kw in low for kw in _OFFER_KEYWORDS)
    has_offer_tag = any(t in ["freelance", "hiring", "jobs", "job-offer"] for t in tags)
    return has_offer_kw or has_offer_tag


async def get_stackoverflow_fr_jobs() -> list:
    print("🕷️  [StackOverflow FR] Scraping API en cours...")
    jobs: list = []
    seen_ids: set = set()

    for search in _SEARCHES[:2]:  # 2 requêtes max pour rester sous la limite
        try:
            params = {
                **search,
                "pagesize": 20,
                "page":     1,
                "filter":   "default",
            }
            resp = await async_fetch(
                f"{BASE_URL}/questions",
                headers=HEADERS,
                params=params,
                timeout=15,
            )
            resp.raise_for_status()
            data  = resp.json()
            items = data.get("items", [])

            for item in items:
                qid    = item.get("question_id", 0)
                title  = (item.get("title") or "").strip()
                tags   = item.get("tags", [])
                link   = item.get("link") or f"https://stackoverflow.com/q/{qid}"
                score  = item.get("score", 0)

                if not title or qid in seen_ids:
                    continue

                # Filtre : ne garder que les questions qui ressemblent à des offres
                if not _is_offer(title, tags):
                    continue

                # Filtre qualité : ignorer les questions très négatives
                if score < -5:
                    continue

                seen_ids.add(qid)
                jobs.append({
                    "title":       title,
                    "description": f"Tags: {', '.join(tags)}" if tags else "",
                    "url":         link,
                    "budget_raw":  "",
                    "source":      "stackoverflow",
                })

            # Respect du quota API (throttle recommandé)
            await asyncio.sleep(max(settings.REQUEST_DELAY, 1.0))

        except Exception as exc:
            print(f"  ⚠️  [StackOverflow] API: {exc}")

    print(f"  ✅ [StackOverflow FR] {len(jobs)} missions trouvées")
    return jobs
