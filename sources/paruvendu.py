# =============================================================
# sources/paruvendu.py — ParuVendu (annonces informatique)
# =============================================================
#
# ParuVendu est un site d'annonces généraliste FR (groupe Le Figaro).
# La section "Services > Informatique" contient des annonces
# de particuliers et pros cherchant des développeurs / webmasters.
#
# URL : https://www.paruvendu.fr/informatique-multimedias/
# =============================================================

import asyncio
import requests
from bs4 import BeautifulSoup
from config.settings import settings
from sources.utils import async_fetch

BASE_URL  = "https://www.paruvendu.fr"
# Catégories services informatiques
LIST_URLS = [
    f"{BASE_URL}/offre-emploi/informatique/",
    f"{BASE_URL}/services-aux-particuliers/informatique-internet/",
    f"{BASE_URL}/informatique-multimedias/",
]
HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Referer":         BASE_URL,
}

_CARD_SELECTORS  = [
    "[class*='annonce']", "[class*='listing-item']",
    ".ad-item", "article", "[class*='item']", "[class*='offer']",
]
_TITLE_SELECTORS = ["h2 a", "h3 a", ".title a", "[class*='title'] a", "h2", "h3"]
_PRICE_SELECTORS = ["[class*='price']", ".price", ".tarif", "[class*='tarif']"]
_DESC_SELECTORS  = [".description", ".desc", "p.summary", "p"]

_OFFER_KEYWORDS = [
    "cherche", "recherche", "développeur", "webmaster", "wordpress",
    "shopify", "création", "refonte", "site web", "seo", "freelance",
    "prestataire", "mission", "informatique",
]


def _is_relevant(title: str, desc: str = "") -> bool:
    text = (title + " " + desc).lower()
    return any(kw in text for kw in _OFFER_KEYWORDS)


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


async def get_paruvendu_jobs() -> list:
    print("🕷️  [ParuVendu] Scraping en cours...")
    jobs: list = []
    seen_urls: set = set()

    for page_url in LIST_URLS:
        try:
            resp = await async_fetch(page_url, headers=HEADERS, timeout=20)
            if resp.status_code in (404, 403, 503):
                continue
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Cherche des blocs annonce
            cards = []
            for sel in _CARD_SELECTORS:
                cards = soup.select(sel)
                if len(cards) >= 3:
                    break

            # Fallback : liens directs vers annonces
            if not cards:
                for a in soup.select("a[href*='/annonce'], a[href*='/ad/'], a[href*='/offre']")[:25]:
                    title = a.get_text(strip=True)
                    href  = _abs(a.get("href", ""))
                    if title and href and len(title) > 8 and href not in seen_urls and _is_relevant(title):
                        seen_urls.add(href)
                        jobs.append({
                            "title":       title,
                            "description": "",
                            "url":         href,
                            "budget_raw":  "",
                            "source":      "paruvendu",
                        })
                await asyncio.sleep(settings.REQUEST_DELAY)
                continue

            for card in cards[:20]:
                try:
                    title_el = _first(card, _TITLE_SELECTORS)
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)
                    if len(title) < 8:
                        continue

                    if title_el.name == "a":
                        href = title_el.get("href", "")
                    else:
                        a = card.select_one("a")
                        href = a.get("href", "") if a else ""
                    link = _abs(href)

                    if not link or link in seen_urls:
                        continue

                    desc_el  = _first(card, _DESC_SELECTORS)
                    desc     = desc_el.get_text(strip=True)[:400] if desc_el else ""

                    price_el = _first(card, _PRICE_SELECTORS)
                    price    = price_el.get_text(strip=True) if price_el else ""

                    if not _is_relevant(title, desc):
                        continue

                    seen_urls.add(link)
                    jobs.append({
                        "title":       title,
                        "description": desc,
                        "url":         link,
                        "budget_raw":  price,
                        "source":      "paruvendu",
                    })
                except Exception as exc:
                    print(f"  ⚠️  [ParuVendu] card: {exc}")

            await asyncio.sleep(settings.REQUEST_DELAY)

        except requests.RequestException as exc:
            print(f"  ❌ [ParuVendu] {page_url}: {exc}")
        except Exception as exc:
            print(f"  ⚠️  [ParuVendu] parsing: {exc}")

    print(f"  ✅ [ParuVendu] {len(jobs)} missions trouvées")
    return jobs
