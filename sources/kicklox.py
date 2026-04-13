# =============================================================
# sources/kicklox.py — scraper Kicklox (freelances IT France)
# =============================================================
#
# Kicklox est une plateforme française spécialisée IT/tech.
# Elle publie des missions sur son jobboard public.
# URL : https://kicklox.com/blog-candidat/offres-missions-freelance/
# ou   : https://kicklox.com/missions/
#
# Le site a un HTML relativement standard (pas de JS lourd),
# accessible avec requests + BeautifulSoup.
# =============================================================

import asyncio
import requests
from bs4 import BeautifulSoup
from config.settings import settings

BASE_URL  = "https://kicklox.com"
LIST_URLS = [
    f"{BASE_URL}/missions/",
    f"{BASE_URL}/offres-freelance/",
    f"{BASE_URL}/blog-candidat/offres-missions-freelance/",
]
HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Referer":         BASE_URL,
}

_CARD_SELECTORS  = [
    ".job-item", ".mission-item", ".offer-item",
    "[class*='job']", "[class*='mission']",
    "article", ".card",
]
_TITLE_SELECTORS = ["h2 a", "h3 a", ".title a", "h2", "h3", ".job-title"]
_DESC_SELECTORS  = [".description", ".excerpt", "p.summary", "p"]
_TJM_SELECTORS   = [".tjm", ".salary", "[class*='tjm']", "[class*='rate']"]
_TECH_SELECTORS  = [".technologies", ".tags", ".skills", "[class*='tag']"]


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


def _fetch(url: str) -> list:
    jobs = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        cards = []
        for sel in _CARD_SELECTORS:
            cards = soup.select(sel)
            if len(cards) >= 2:
                break

        # Fallback liens directs
        if not cards:
            for a in soup.select("a[href*='mission'], a[href*='offre'], a[href*='freelance']")[:20]:
                title = a.get_text(strip=True)
                href  = _abs(a.get("href", ""))
                if title and href and len(title) > 8:
                    jobs.append({
                        "title": title, "description": "",
                        "url": href, "budget_raw": "", "source": "kicklox",
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

                desc_el  = _first(card, _DESC_SELECTORS)
                desc     = desc_el.get_text(strip=True)[:500] if desc_el else ""

                tjm_el   = _first(card, _TJM_SELECTORS)
                tjm      = tjm_el.get_text(strip=True) if tjm_el else ""

                tech_el  = _first(card, _TECH_SELECTORS)
                tech     = tech_el.get_text(strip=True) if tech_el else ""

                if not desc and tech:
                    desc = tech

                if title and link:
                    jobs.append({
                        "title":       title,
                        "description": desc,
                        "url":         link,
                        "budget_raw":  tjm,
                        "source":      "kicklox",
                    })
            except Exception as exc:
                print(f"  ⚠️  [Kicklox] card: {exc}")

    except requests.RequestException as exc:
        print(f"  ❌ [Kicklox] réseau {url}: {exc}")

    return jobs


async def get_kicklox_jobs() -> list:
    print("🕷️  [Kicklox] Scraping en cours...")

    all_jobs:  list = []
    seen_urls: set  = set()

    for url in LIST_URLS:
        batch = await asyncio.to_thread(_fetch, url)
        for job in batch:
            if job["url"] not in seen_urls:
                seen_urls.add(job["url"])
                all_jobs.append(job)
        if batch:          # on s'arrête à la première URL qui répond
            break
        await asyncio.sleep(settings.REQUEST_DELAY)

    print(f"  ✅ [Kicklox] {len(all_jobs)} missions trouvées")
    return all_jobs
