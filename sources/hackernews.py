# =============================================================
# sources/hackernews.py — HackerNews "Who's Hiring" via Algolia
# =============================================================
#
# Chaque mois, HackerNews publie un thread "Ask HN: Who is hiring?"
# L'API Algolia indexe tous ces commentaires (les offres) en temps
# réel et est totalement publique, sans auth.
#
# Stratégie :
#  1. Récupérer l'ID du thread "Who is hiring" le plus récent
#  2. Requêter l'API Algolia pour les commentaires de ce thread
#  3. Filtrer par mots-clés tech (dev web, remote, freelance)
#  4. Chaque commentaire = une offre de job
#
# Endpoints :
#   Algolia : https://hn.algolia.com/api/v1/search_by_date
#   HN Item : https://hacker-news.firebaseio.com/v0/item/{id}.json
# =============================================================

import asyncio
import re
import requests
from config.settings import settings

ALGOLIA_URL  = "https://hn.algolia.com/api/v1/search_by_date"
HN_ITEM_URL  = "https://hacker-news.firebaseio.com/v0/item/{}.json"
HN_POST_URL  = "https://news.ycombinator.com/item?id={}"
HEADERS      = {"User-Agent": "MissionAgentBot/1.0 (personal freelance tracker)"}

# Mots-clés qui signalent une offre pertinente pour dev web freelance
_TECH_KEYWORDS = {
    "javascript", "typescript", "react", "vue", "angular", "next.js", "nextjs",
    "node.js", "nodejs", "python", "django", "fastapi", "flask",
    "php", "laravel", "wordpress", "ruby", "rails",
    "frontend", "backend", "fullstack", "full-stack", "full stack",
    "web developer", "software engineer", "remote", "freelance",
    "css", "html", "graphql", "rest api", "devops", "seo",
}

_EXCLUDE_KEYWORDS = {
    "onsite only", "no remote", "office only", "relocation required",
}


def _is_relevant(text: str) -> bool:
    """Retourne True si le commentaire ressemble à une offre dev web."""
    low = text.lower()
    if any(ex in low for ex in _EXCLUDE_KEYWORDS):
        return False
    return any(kw in low for kw in _TECH_KEYWORDS)


def _clean_text(raw: str) -> str:
    """Nettoie le HTML des commentaires HN."""
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;",  "<", text)
    text = re.sub(r"&gt;",  ">", text)
    text = re.sub(r"&quot;","\"",text)
    text = re.sub(r"&#x27;","'", text)
    text = re.sub(r"\s+",   " ", text).strip()
    return text[:500]


def _extract_title(text: str, max_len: int = 120) -> str:
    """Extrait un titre lisible depuis le texte du post HN."""
    clean = re.sub(r"<[^>]+>", " ", text or "")
    clean = re.sub(r"\s+", " ", clean).strip()
    # Prend la première ligne non-vide
    for line in clean.splitlines():
        line = line.strip()
        if len(line) > 10:
            return line[:max_len]
    return clean[:max_len]


def _fetch_who_is_hiring_thread_id() -> int | None:
    """Récupère l'ID du thread 'Ask HN: Who is hiring?' le plus récent."""
    try:
        params = {
            "query":       "Ask HN: Who is hiring?",
            "tags":        "story,ask_hn",
            "hitsPerPage": 5,
        }
        resp = requests.get(
            "https://hn.algolia.com/api/v1/search",
            params=params,
            headers=HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
        # Premier résultat = le plus récent
        for hit in hits:
            title = (hit.get("title") or "").lower()
            if "who is hiring" in title:
                return int(hit["objectID"])
    except Exception as exc:
        print(f"  ⚠️  [HackerNews] Impossible de trouver le thread: {exc}")
    return None


def _fetch_jobs_from_thread(thread_id: int, max_items: int = 40) -> list:
    """Récupère les commentaires (offres) d'un thread HN."""
    jobs = []
    try:
        params = {
            "tags":        f"comment,story_{thread_id}",
            "hitsPerPage": max_items,
        }
        resp = requests.get(ALGOLIA_URL, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        hits = resp.json().get("hits", [])

        for hit in hits:
            raw_text = hit.get("comment_text") or hit.get("story_text") or ""
            if not raw_text:
                continue

            if not _is_relevant(raw_text):
                continue

            obj_id   = hit.get("objectID", "")
            url      = HN_POST_URL.format(f"{thread_id}?id={obj_id}") if obj_id else HN_POST_URL.format(thread_id)
            title    = _extract_title(raw_text)
            desc     = _clean_text(raw_text)
            date     = hit.get("created_at", "")

            if title and url:
                jobs.append({
                    "title":       title,
                    "description": desc,
                    "url":         url,
                    "budget_raw":  "",
                    "source":      "hackernews",
                    "date":        date,
                })

    except Exception as exc:
        print(f"  ⚠️  [HackerNews] Erreur fetch commentaires: {exc}")

    return jobs


async def get_hackernews_jobs() -> list:
    print("🕷️  [HackerNews] Scraping en cours...")

    # Chercher l'ID du thread courant
    try:
        thread_id = await asyncio.to_thread(_fetch_who_is_hiring_thread_id)
    except Exception as exc:
        print(f"  ⚠️  [HackerNews] to_thread fetch_thread: {exc}")
        thread_id = None
    if not thread_id:
        print("  ⚠️  [HackerNews] Thread non trouvé, fallback sur ID connu")
        # Fallback sur une recherche directe par tags
        thread_id = None

    raw_jobs: list = []

    if thread_id:
        try:
            raw_jobs = await asyncio.to_thread(_fetch_jobs_from_thread, thread_id)
        except Exception as exc:
            print(f"  ⚠️  [HackerNews] to_thread fetch_jobs: {exc}")
            raw_jobs = []
    else:
        # Fallback : chercher directement les commentaires "hiring" récents
        try:
            params = {
                "query":       "hiring remote developer",
                "tags":        "ask_hn",
                "hitsPerPage": 20,
            }
            resp = requests.get(ALGOLIA_URL, params=params, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            hits = resp.json().get("hits", [])
            for hit in hits:
                raw = hit.get("story_text") or hit.get("comment_text") or ""
                if not raw or not _is_relevant(raw):
                    continue
                obj_id = hit.get("objectID", "")
                raw_jobs.append({
                    "title":       _extract_title(raw),
                    "description": _clean_text(raw),
                    "url":         HN_POST_URL.format(obj_id),
                    "budget_raw":  "",
                    "source":      "hackernews",
                    "date":        hit.get("created_at", ""),
                })
        except Exception as exc:
            print(f"  ❌ [HackerNews] Fallback échoué: {exc}")

    # Déduplication par URL
    seen_urls: set = set()
    jobs: list = []
    for job in raw_jobs:
        url = job.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            jobs.append(job)

    await asyncio.sleep(settings.REQUEST_DELAY)
    print(f"  ✅ [HackerNews] {len(jobs)} missions trouvées")
    return jobs
