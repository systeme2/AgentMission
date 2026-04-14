# =============================================================
# sources/befreelancr.py — scraper BeFreelancr
# =============================================================
#
# BeFreelancr est une place de marché FR (TPE/PME ↔ freelances).
# Modèle similaire à Fiverr : le freelance crée son service,
# le client commande. On scrape les demandes récentes.
#
# URL cible : https://www.befreelancr.com/missions
# =============================================================

import asyncio
import requests
from bs4 import BeautifulSoup
from config.settings import settings
from sources.utils import async_fetch

BASE_URL = "https://www.befreelancr.com"
LIST_URL = f"{BASE_URL}/missions"
HEADERS  = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Referer":         BASE_URL,
}

_CARD_SELECTORS   = [
    ".mission-card", ".mission-item", "[class*='mission']",
    ".offer-card", "article.mission", "article", ".card",
]
_TITLE_SELECTORS  = ["h2 a", "h3 a", ".mission-title a", ".title a", "h2", "h3"]
_DESC_SELECTORS   = [".mission-description", ".description", ".excerpt", "p.desc", "p"]
_BUDGET_SELECTORS = [".budget", ".price", "[class*='budget']", "[class*='prix']"]
_DATE_SELECTORS   = ["time", ".date", "[class*='date']", ".published"]


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


async def get_befreelancr_jobs() -> list:
    print("🕷️  [BeFreelancr] Scraping en cours...")
    jobs = []

    try:
        resp = await async_fetch(LIST_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        cards = []
        for sel in _CARD_SELECTORS:
            cards = soup.select(sel)
            if len(cards) >= 3:
                break

        # Fallback : cards génériques
        if not cards:
            cards = soup.select("[class*='card'], [class*='item'], [class*='offer']")

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

                desc_el   = _first(card, _DESC_SELECTORS)
                desc      = desc_el.get_text(strip=True)[:500] if desc_el else ""

                budget_el = _first(card, _BUDGET_SELECTORS)
                budget    = budget_el.get_text(strip=True) if budget_el else ""

                date_el   = _first(card, _DATE_SELECTORS)
                date_str  = (
                    date_el.get("datetime") or date_el.get_text(strip=True)
                    if date_el else ""
                )

                if title and link:
                    jobs.append({
                        "title":       title,
                        "description": desc,
                        "url":         link,
                        "budget_raw":  budget,
                        "source":      "befreelancr",
                        "date":        date_str,
                    })
            except Exception as exc:
                print(f"  ⚠️  [BeFreelancr] parsing: {exc}")

        await asyncio.sleep(settings.REQUEST_DELAY)

    except requests.RequestException as exc:
        print(f"  ❌ [BeFreelancr] Erreur réseau: {exc}")

    print(f"  ✅ [BeFreelancr] {len(jobs)} missions trouvées")
    return jobs
