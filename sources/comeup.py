# =============================================================
# sources/comeup.py — scraper ComeUp (ex 5euros.com)
# =============================================================
#
# ComeUp est la principale plateforme française de micro-services.
# Elle expose une section "demandes" où les clients postent leurs
# besoins — c'est là qu'on cherche des missions pour freelances.
#
# URL cible : https://comeup.com/fr/services (marketplace services)
# + section recherche de prestataires par les clients
# =============================================================

import asyncio
import requests
from bs4 import BeautifulSoup
from config.settings import settings

BASE_URL     = "https://comeup.com"
# Page où les clients cherchent des prestataires
SEARCH_URL   = f"{BASE_URL}/fr/services"
HEADERS      = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Referer":         BASE_URL,
}

# Catégories tech à scraper
TECH_CATEGORIES = [
    "/fr/services/creation-site-web",
    "/fr/services/développement-web",
    "/fr/services/seo-referencement",
    "/fr/services/logo-identite-visuelle",
]

_CARD_SELECTORS  = [".service-card", "[class*='service-card']", ".offer", "article", "[class*='item']"]
_TITLE_SELECTORS = ["h3 a", "h2 a", ".title a", "a.service-name", "h3", "h2"]
_PRICE_SELECTORS = [".price", "[class*='price']", "[class*='prix']", ".amount"]
_DESC_SELECTORS  = [".description", ".subtitle", "p.desc", "p"]


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


async def get_comeup_jobs() -> list:
    print("🕷️  [ComeUp] Scraping en cours...")
    jobs = []
    seen_urls: set = set()

    urls_to_scrape = [SEARCH_URL] + [BASE_URL + cat for cat in TECH_CATEGORIES[:2]]

    for page_url in urls_to_scrape:
        try:
            resp = requests.get(page_url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            cards = []
            for sel in _CARD_SELECTORS:
                cards = soup.select(sel)
                if len(cards) >= 3:
                    break

            for card in cards:
                try:
                    title_el = _first(card, _TITLE_SELECTORS)
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)
                    if len(title) < 5:
                        continue

                    # Lien
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
                        "source":      "comeup",
                    })
                except Exception as exc:
                    print(f"  ⚠️  [ComeUp] parsing card: {exc}")

            await asyncio.sleep(settings.REQUEST_DELAY)

        except requests.RequestException as exc:
            print(f"  ❌ [ComeUp] {page_url}: {exc}")

    print(f"  ✅ [ComeUp] {len(jobs)} missions trouvées")
    return jobs
