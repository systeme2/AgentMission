# =============================================================
# sources/fiverr.py — scraper Fiverr (recherche de services)
# =============================================================
#
# Fiverr est une marketplace internationale où les freelances
# proposent des "gigs". On cible les catégories tech :
#   - Programming & Tech
#   - Digital Marketing (SEO)
#   - Website Builders
#
# Strategy : scraper les résultats de recherche par catégorie
# via les URL publiques de recherche. La page HTML contient
# les données dans une balise <script type="application/ld+json">
# ou directement dans des cards HTML.
# =============================================================

import asyncio
import json
import re
import requests
from bs4 import BeautifulSoup
from config.settings import settings

BASE_URL = "https://www.fiverr.com"
HEADERS  = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer":         "https://www.fiverr.com/",
}

# Catégories / recherches ciblées
_SEARCH_URLS = [
    f"{BASE_URL}/search/gigs?query=wordpress+developer&source=top-bar",
    f"{BASE_URL}/search/gigs?query=react+developer&source=top-bar",
    f"{BASE_URL}/search/gigs?query=website+seo&source=top-bar",
]

_CARD_SELECTORS = [
    "[class*='gig-card']", "[class*='GigCard']",
    "article.gig-wrapper", ".gig-wrapper",
    "[data-impression-collected]", "article",
]
_TITLE_SELECTORS = [
    "a[class*='title']", ".gig-title a", "h3 a",
    "[class*='title'] a", "a[class*='gig-title']",
    "h3", "h2",
]
_PRICE_SELECTORS = [
    "[class*='price']", "[class*='Price']",
    ".price-wrapper", "footer [class*='price']",
]
_SELLER_SELECTORS = [
    "[class*='seller-name']", "[class*='username']",
    "a[class*='seller']", ".seller-name",
]


def _try_json_ld(soup: BeautifulSoup) -> list:
    """Extrait les gigs depuis les blocs JSON-LD si présents."""
    jobs = []
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") not in ("Product", "Service", "Offer"):
                    continue
                name  = item.get("name", "")
                url   = item.get("url", "")
                desc  = item.get("description", "")[:500]
                price = ""
                offers = item.get("offers", {})
                if isinstance(offers, dict):
                    price = str(offers.get("price", ""))
                    curr  = offers.get("priceCurrency", "$")
                    price = f"{curr}{price}" if price else ""

                if name and url:
                    jobs.append({
                        "title":       name,
                        "description": desc,
                        "url":         url if url.startswith("http") else BASE_URL + url,
                        "budget_raw":  price,
                        "source":      "fiverr",
                    })
        except (json.JSONDecodeError, AttributeError):
            continue
    return jobs


def _first(el, selectors):
    for sel in selectors:
        found = el.select_one(sel)
        if found:
            return found
    return None


def _fetch_page(url: str) -> list:
    jobs = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Tentative JSON-LD en premier
        json_jobs = _try_json_ld(soup)
        if json_jobs:
            return json_jobs

        # Fallback HTML scraping
        cards = []
        for sel in _CARD_SELECTORS:
            cards = soup.select(sel)
            if len(cards) >= 3:
                break

        for card in cards[:20]:
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
                link = href if href.startswith("http") else BASE_URL + href

                price_el  = _first(card, _PRICE_SELECTORS)
                price     = price_el.get_text(strip=True) if price_el else ""

                seller_el = _first(card, _SELLER_SELECTORS)
                seller    = seller_el.get_text(strip=True) if seller_el else ""

                desc = f"Gig Fiverr par {seller}" if seller else ""

                if title and link:
                    jobs.append({
                        "title":       title,
                        "description": desc,
                        "url":         link,
                        "budget_raw":  price,
                        "source":      "fiverr",
                    })
            except Exception as exc:
                print(f"  ⚠️  [Fiverr] card: {exc}")

    except requests.RequestException as exc:
        print(f"  ❌ [Fiverr] réseau {url}: {exc}")

    return jobs


async def get_fiverr_jobs() -> list:
    print("🕷️  [Fiverr] Scraping en cours...")

    all_jobs:  list = []
    seen_urls: set  = set()

    for url in _SEARCH_URLS:
        batch = await asyncio.to_thread(_fetch_page, url)
        for job in batch:
            if job["url"] not in seen_urls:
                seen_urls.add(job["url"])
                all_jobs.append(job)
        await asyncio.sleep(settings.REQUEST_DELAY)

    print(f"  ✅ [Fiverr] {len(all_jobs)} missions trouvées")
    return all_jobs
