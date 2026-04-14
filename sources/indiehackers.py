# =============================================================
# sources/indiehackers.py — scraper IndieHackers
# =============================================================
#
# IndieHackers est une communauté de fondateurs / indie makers.
# Le forum contient régulièrement des offres de missions et
# des recherches de collaborateurs sur deux sections :
#
#   /jobs        → offres d'emploi / missions
#   /groups/     → groupes thématiques avec annonces
#   /forum       → posts "looking for developer" etc.
#
# Le site est rendu en HTML standard (Next.js SSR) avec les
# données dans __NEXT_DATA__ → on les extrait en JSON.
# =============================================================

import asyncio
import json
import re
import requests
from bs4 import BeautifulSoup
from config.settings import settings
from sources.utils import async_fetch

BASE_URL  = "https://www.indiehackers.com"
LIST_URLS = [
    f"{BASE_URL}/jobs",
    f"{BASE_URL}/forum/post/looking-for-a-developer",
    f"{BASE_URL}/forum",
]
HEADERS   = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
}

_CARD_SELECTORS  = [
    ".job-listing", "[class*='job']", "[class*='Job']",
    ".post-item", "[class*='post-item']", "article",
]
_TITLE_SELECTORS = ["h2 a", "h3 a", ".title a", "a.job-title", "h2", "h3"]
_DESC_SELECTORS  = [".description", ".body", "p.excerpt", "p"]
_COMP_SELECTORS  = [".company", "[class*='company']", ".employer"]

_HIRING_KEYWORDS = [
    "hiring", "looking for", "developer wanted", "engineer wanted",
    "need a developer", "seeking developer", "job", "position",
    "remote", "freelance", "contract",
]


def _abs(href: str) -> str:
    if not href:
        return ""
    return href if href.startswith("http") else BASE_URL + href


def _first(el, selectors):
    for sel in selectors:
        found = el.select_one(sel)
        if found:
            return found
    return None


def _is_relevant(text: str) -> bool:
    low = text.lower()
    return any(kw in low for kw in _HIRING_KEYWORDS)


def _parse_next_data(soup: BeautifulSoup) -> list:
    """Extrait les jobs depuis __NEXT_DATA__ si disponible."""
    jobs = []
    script = soup.find("script", {"id": "__NEXT_DATA__"})
    if not script or not script.string:
        return jobs

    try:
        payload    = json.loads(script.string)
        page_props = payload.get("props", {}).get("pageProps", {})

        # Cherche des listes de jobs dans les props
        candidates = []
        for key in ("jobs", "listings", "posts", "items", "data"):
            val = page_props.get(key)
            if isinstance(val, list) and val:
                candidates = val
                break

        for item in candidates[:30]:
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or item.get("name") or "").strip()
            url   = (item.get("url")   or item.get("link") or "").strip()
            desc  = (item.get("description") or item.get("body") or "").strip()[:500]

            if not url.startswith("http"):
                slug = item.get("slug") or item.get("id") or ""
                url  = f"{BASE_URL}/jobs/{slug}" if slug else ""

            if title and url and _is_relevant(title + " " + desc):
                jobs.append({
                    "title":       title,
                    "description": desc,
                    "url":         url,
                    "budget_raw":  str(item.get("salary") or ""),
                    "source":      "indiehackers",
                })
    except (json.JSONDecodeError, AttributeError, KeyError):
        pass

    return jobs


def _fetch(url: str) -> list:
    """Synchronous fetch — appelé via asyncio.to_thread dans get_indiehackers_jobs."""
    jobs = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Tentative __NEXT_DATA__
        next_jobs = _parse_next_data(soup)
        if next_jobs:
            return next_jobs

        # Fallback HTML scraping
        cards = []
        for sel in _CARD_SELECTORS:
            cards = soup.select(sel)
            if len(cards) >= 2:
                break

        # Fallback liens directs
        if not cards:
            for a in soup.select("a[href*='/jobs/'], a[href*='/post/']")[:20]:
                title = a.get_text(strip=True)
                href  = _abs(a.get("href", ""))
                if title and href and len(title) > 8 and _is_relevant(title):
                    jobs.append({
                        "title": title, "description": "",
                        "url": href, "budget_raw": "", "source": "indiehackers",
                    })
            return jobs

        for card in cards:
            try:
                title_el = _first(card, _TITLE_SELECTORS)
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if len(title) < 5:
                    continue

                if title_el.name == "a":
                    href = title_el.get("href", "")
                else:
                    a = card.select_one("a")
                    href = a.get("href", "") if a else ""
                link = _abs(href)

                desc_el = _first(card, _DESC_SELECTORS)
                desc    = desc_el.get_text(strip=True)[:500] if desc_el else ""

                comp_el = _first(card, _COMP_SELECTORS)
                company = comp_el.get_text(strip=True) if comp_el else ""

                full_title = f"{title} @ {company}".strip(" @") if company else title

                if full_title and link and _is_relevant(full_title + " " + desc):
                    jobs.append({
                        "title":       full_title,
                        "description": desc,
                        "url":         link,
                        "budget_raw":  "",
                        "source":      "indiehackers",
                    })
            except Exception as exc:
                print(f"  ⚠️  [IndieHackers] card: {exc}")

    except requests.RequestException as exc:
        print(f"  ❌ [IndieHackers] réseau {url}: {exc}")

    return jobs


async def get_indiehackers_jobs() -> list:
    print("🕷️  [IndieHackers] Scraping en cours...")

    all_jobs:  list = []
    seen_urls: set  = set()

    for url in LIST_URLS:
        try:
            batch = await asyncio.to_thread(_fetch, url)
            for job in batch:
                if job["url"] not in seen_urls:
                    seen_urls.add(job["url"])
                    all_jobs.append(job)
            if batch:
                break   # S'arrête à la première URL productive
        except Exception as exc:
            print(f"  ⚠️  [IndieHackers] {url}: {exc}")
        await asyncio.sleep(settings.REQUEST_DELAY)

    print(f"  ✅ [IndieHackers] {len(all_jobs)} missions trouvées")
    return all_jobs
