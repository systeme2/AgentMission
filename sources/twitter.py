# =============================================================
# sources/twitter.py — Twitter/X via API v2 + fallback Nitter
# =============================================================
#
# Twitter/X est la source la plus difficile :
#   - API v2 : Bearer Token requis (compte dev gratuit suffit)
#     Variable d'env : TWITTER_BEARER_TOKEN
#   - Sans token → fallback Nitter (instances publiques RSS)
#   - Sans Nitter → scraping HTML recherche publique (limité)
#
# On cherche les tweets contenant :
#   "freelance developer" "hiring" OR "we're hiring" OR "job"
#   depuis les dernières 24h, langue FR ou EN
#
# Rate limits API v2 (tier gratuit) :
#   - 500k tweets/mois lus
#   - 1 requête / 15 sec sur /recent/search
# =============================================================

import asyncio
import os
import re
import xml.etree.ElementTree as ET
import requests
from config.settings import settings

# ── Config ────────────────────────────────────────────────────
BEARER_TOKEN  = os.getenv("TWITTER_BEARER_TOKEN", "")
API_V2_URL    = "https://api.twitter.com/2/tweets/search/recent"

# Instances Nitter publiques (fallback sans API key)
# On essaie dans l'ordre jusqu'à en trouver une qui répond
NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
]

HEADERS_API = {
    "Authorization": f"Bearer {BEARER_TOKEN}",
    "User-Agent":    "MissionAgentBot/1.0",
}
HEADERS_HTML = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

# Requêtes de recherche Twitter
_QUERIES = [
    '("freelance developer" OR "développeur freelance") (hiring OR mission OR "looking for") -is:retweet lang:fr',
    '(wordpress OR react OR nextjs) (freelance OR remote) hiring -is:retweet lang:en',
    '(#hiring OR #freelance) (developer OR développeur) -is:retweet',
]

# Requêtes Nitter (plus simples, pas de syntaxe avancée)
_NITTER_SEARCHES = [
    "freelance developer hiring",
    "développeur freelance mission",
]

_HIRING_KEYWORDS = [
    "hiring", "looking for", "we need", "job offer", "mission",
    "freelance", "developer wanted", "dev wanted", "développeur",
]


def _is_relevant_tweet(text: str) -> bool:
    low = text.lower()
    return any(kw in low for kw in _HIRING_KEYWORDS)


def _tweet_to_job(tweet_id: str, text: str, created_at: str = "") -> dict | None:
    """Convertit un tweet en job dict."""
    if not _is_relevant_tweet(text):
        return None
    clean = re.sub(r"https?://\S+", "", text).strip()
    clean = re.sub(r"\s+", " ", clean)
    title = clean[:100] if clean else "Tweet"
    return {
        "title":       title,
        "description": clean[:500],
        "url":         f"https://twitter.com/i/web/status/{tweet_id}",
        "budget_raw":  "",
        "source":      "twitter",
        "date":        created_at,
    }


# ── Méthode 1 : API v2 ────────────────────────────────────────

def _fetch_api_v2(query: str, max_results: int = 20) -> list:
    """Requête l'API Twitter v2 (nécessite TWITTER_BEARER_TOKEN)."""
    if not BEARER_TOKEN:
        raise ValueError("TWITTER_BEARER_TOKEN non défini")

    params = {
        "query":       query,
        "max_results": min(max_results, 100),
        "tweet.fields":"created_at,text",
        "sort_order":  "recency",
    }
    resp = requests.get(API_V2_URL, params=params, headers=HEADERS_API, timeout=15)

    if resp.status_code == 401:
        raise PermissionError("Token Twitter invalide ou expiré")
    if resp.status_code == 429:
        raise RuntimeError("Rate limit Twitter atteint — réessayez dans 15 min")
    resp.raise_for_status()

    data   = resp.json()
    tweets = data.get("data") or []
    jobs   = []
    for tw in tweets:
        job = _tweet_to_job(tw.get("id", ""), tw.get("text", ""), tw.get("created_at", ""))
        if job:
            jobs.append(job)
    return jobs


# ── Méthode 2 : Nitter RSS ────────────────────────────────────

def _fetch_nitter_rss(search: str, instance: str) -> list:
    """Scrape le flux RSS d'une instance Nitter."""
    jobs = []
    url  = f"{instance}/search/rss?q={requests.utils.quote(search)}&f=tweets"
    try:
        resp = requests.get(url, headers=HEADERS_HTML, timeout=10)
        resp.raise_for_status()
        root  = ET.fromstring(resp.content)
        items = root.findall(".//item")
        for item in items[:20]:
            title  = (item.findtext("title") or "").strip()
            link   = (item.findtext("link")  or "").strip()
            desc   = (item.findtext("description") or "").strip()[:500]
            pub    = (item.findtext("pubDate") or "").strip()

            # Extraire l'ID depuis le lien Nitter
            tweet_id = re.search(r"/status/(\d+)", link)
            tweet_id = tweet_id.group(1) if tweet_id else ""
            tw_url   = f"https://twitter.com/i/web/status/{tweet_id}" if tweet_id else link

            text = re.sub(r"<[^>]+>", " ", desc)
            if not _is_relevant_tweet(text) and not _is_relevant_tweet(title):
                continue

            jobs.append({
                "title":       title[:120] or text[:120],
                "description": re.sub(r"<[^>]+>", " ", desc)[:500],
                "url":         tw_url,
                "budget_raw":  "",
                "source":      "twitter",
                "date":        pub,
            })
    except (ET.ParseError, requests.RequestException):
        pass  # silencieux — instance peut être down
    return jobs


def _try_nitter(search: str) -> list:
    """Essaie les instances Nitter dans l'ordre."""
    for instance in NITTER_INSTANCES:
        try:
            jobs = _fetch_nitter_rss(search, instance)
            if jobs:
                return jobs
        except Exception:
            continue
    return []


# ── Orchestration ─────────────────────────────────────────────

async def get_twitter_jobs() -> list:
    print("🕷️  [Twitter/X] Scraping en cours...")

    all_jobs:  list = []
    seen_urls: set  = set()

    # ── Tentative API v2 ─────────────────────────────────────
    api_ok = False
    if BEARER_TOKEN:
        for query in _QUERIES:
            try:
                batch = await asyncio.to_thread(_fetch_api_v2, query)
                for job in batch:
                    if job["url"] not in seen_urls:
                        seen_urls.add(job["url"])
                        all_jobs.append(job)
                await asyncio.sleep(max(settings.REQUEST_DELAY, 15))  # respect rate limit
                api_ok = True
            except PermissionError as exc:
                print(f"  ⚠️  [Twitter] API auth: {exc}")
                break
            except RuntimeError as exc:
                print(f"  ⚠️  [Twitter] Rate limit: {exc}")
                break
            except Exception as exc:
                print(f"  ⚠️  [Twitter] API query: {exc}")
    else:
        print("  ℹ️  [Twitter] Pas de TWITTER_BEARER_TOKEN → Nitter RSS")

    # ── Fallback Nitter RSS ──────────────────────────────────
    if not api_ok:
        for search in _NITTER_SEARCHES:
            try:
                batch = await asyncio.to_thread(_try_nitter, search)
                for job in batch:
                    if job["url"] not in seen_urls:
                        seen_urls.add(job["url"])
                        all_jobs.append(job)
                await asyncio.sleep(settings.REQUEST_DELAY)
            except Exception as exc:
                print(f"  ⚠️  [Twitter/Nitter] search='{search}': {exc}")

    print(f"  ✅ [Twitter/X] {len(all_jobs)} missions trouvées")
    return all_jobs
