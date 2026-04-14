# =============================================================
# sources/leboncoin.py — scraper Leboncoin (services IT)
# =============================================================
#
# Leboncoin a une section "Services" > "Informatique" où des
# particuliers et professionnels postent leurs besoins en dev.
#
# ATTENTION : Leboncoin a une détection anti-bot agressive.
# On utilise des délais généreux et des headers réalistes.
# Désactivé par défaut dans settings — activer prudemment.
#
# URL : https://www.leboncoin.fr/services/offres/informatique/
# =============================================================

import asyncio
import requests
from bs4 import BeautifulSoup
from config.settings import settings
from sources.utils import async_fetch

BASE_URL = "https://www.leboncoin.fr"
LIST_URL = f"{BASE_URL}/services/offres/informatique/"
HEADERS  = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer":         BASE_URL,
}

_CARD_SELECTORS  = ["[data-qa-id='aditem_container']", "[class*='aditem']", "article", "[class*='item']"]
_TITLE_SELECTORS = ["[data-qa-id='aditem_title']", "h2 a", "h3 a", "p[class*='title']", "h2", "h3"]
_PRICE_SELECTORS = ["[data-qa-id='aditem_price']", "[class*='price']", ".price"]


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


async def get_leboncoin_jobs() -> list:
    print("🕷️  [Leboncoin] Scraping en cours...")
    jobs: list = []

    try:
        resp = await async_fetch(LIST_URL, headers=HEADERS, timeout=25)
        # Leboncoin renvoie souvent une page vide ou captcha
        if resp.status_code in (403, 429, 503):
            print(f"  ⚠️  [Leboncoin] Bloqué (HTTP {resp.status_code}) — anti-bot actif")
            return jobs
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

                a = card.select_one("a")
                href  = a.get("href", "") if a else ""
                link  = _abs(href)

                price_el = _first(card, _PRICE_SELECTORS)
                price    = price_el.get_text(strip=True) if price_el else ""

                if title and link:
                    jobs.append({
                        "title":       title,
                        "description": "",
                        "url":         link,
                        "budget_raw":  price,
                        "source":      "leboncoin",
                    })
            except Exception as exc:
                print(f"  ⚠️  [Leboncoin] card: {exc}")

        await asyncio.sleep(settings.REQUEST_DELAY)

    except requests.RequestException as exc:
        print(f"  ❌ [Leboncoin] Erreur réseau: {exc}")

    print(f"  ✅ [Leboncoin] {len(jobs)} missions trouvées")
    return jobs
