# =============================================================
# sources/cinq_euros.py — scraper 5euros.com
# =============================================================
#
# 5euros.com est une plateforme française de micro-services
# (renommée mais gardant le domaine). Les clients postent
# des demandes de services dans la catégorie informatique.
#
# URL cible : https://5euros.com/services/informatique
# =============================================================

import asyncio
import requests
from bs4 import BeautifulSoup
from config.settings import settings
from sources.utils import async_fetch

BASE_URL = "https://5euros.com"
SEARCH_URLS = [
    f"{BASE_URL}/services/creation-de-site-web",
    f"{BASE_URL}/services/développement-web",
    f"{BASE_URL}/services/referencement-seo",
    f"{BASE_URL}/services/informatique",
]
HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Referer":         BASE_URL,
}

_CARD_SELECTORS  = [".service-card", "[class*='service-card']", ".gig-card", "article", "[class*='gig']"]
_TITLE_SELECTORS = ["h3 a", "h2 a", ".title a", ".service-title a", "h3", "h2"]
_PRICE_SELECTORS = [".price", "[class*='price']", ".amount", "[class*='amount']"]
_DESC_SELECTORS  = [".description", ".subtitle", "p.desc", ".service-desc", "p"]


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


async def get_cinq_euros_jobs() -> list:
    print("🕷️  [5euros] Scraping en cours...")
    jobs: list = []
    seen_urls: set = set()

    for page_url in SEARCH_URLS[:2]:  # 2 catégories max pour limiter les requêtes
        try:
            resp = await async_fetch(page_url, headers=HEADERS, timeout=20)
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

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
                    link = _abs(href)

                    if not link or link in seen_urls:
                        continue
                    seen_urls.add(link)

                    desc_el  = _first(card, _DESC_SELECTORS)
                    desc     = desc_el.get_text(strip=True)[:500] if desc_el else ""

                    price_el = _first(card, _PRICE_SELECTORS)
                    price    = price_el.get_text(strip=True) if price_el else ""

                    jobs.append({
                        "title":       title,
                        "description": desc,
                        "url":         link,
                        "budget_raw":  price,
                        "source":      "5euros",
                    })
                except Exception as exc:
                    print(f"  ⚠️  [5euros] card: {exc}")

            await asyncio.sleep(settings.REQUEST_DELAY)

        except requests.RequestException as exc:
            print(f"  ❌ [5euros] {page_url}: {exc}")

    print(f"  ✅ [5euros] {len(jobs)} missions trouvées")
    return jobs
