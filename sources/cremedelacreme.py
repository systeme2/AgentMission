# =============================================================
# sources/cremedelacreme.py — scraper Crème de la Crème
# =============================================================
#
# Crème de la Crème est une plateforme FR premium pour
# freelances senior (développeurs, designers, data scientists).
# Missions haute valeur ajoutée avec clients triés.
#
# URL : https://cremedelacreme.io/fr/missions
# =============================================================

import asyncio
import json
import requests
from bs4 import BeautifulSoup
from config.settings import settings
from sources.utils import async_fetch

BASE_URL  = "https://cremedelacreme.io"
LIST_URL  = f"{BASE_URL}/fr/missions"
HEADERS   = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer":         BASE_URL,
}

_CARD_SELECTORS  = [".mission-card", "[class*='mission-card']", ".job-card", "article", "[class*='offer']"]
_TITLE_SELECTORS = ["h2 a", "h3 a", ".mission-title a", ".title a", "h2", "h3"]
_DESC_SELECTORS  = [".mission-description", ".description", ".excerpt", "p.desc", "p"]
_TJM_SELECTORS   = [".tjm", ".daily-rate", "[class*='tjm']", "[class*='rate']", ".salary"]
_TECH_SELECTORS  = [".technologies", ".skills", ".tags", "[class*='tag']", "[class*='tech']"]


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


async def get_cremedelacreme_jobs() -> list:
    print("🕷️  [CrèmeDeLaCrème] Scraping en cours...")
    jobs: list = []

    try:
        resp = await async_fetch(LIST_URL, headers=HEADERS, timeout=20)
        if resp.status_code == 404:
            print("  ⚠️  [CrèmeDeLaCrème] Page non trouvée (URL peut avoir changé)")
            return jobs
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Tentative Next.js __NEXT_DATA__
        next_data = soup.find("script", {"id": "__NEXT_DATA__"})
        if next_data:
            try:
                payload    = json.loads(next_data.string)
                page_props = payload.get("props", {}).get("pageProps", {})
                for key in ("missions", "jobs", "offers", "data"):
                    items = page_props.get(key, [])
                    if isinstance(items, list) and items:
                        for item in items[:20]:
                            if not isinstance(item, dict):
                                continue
                            title   = (item.get("title") or item.get("name") or "").strip()
                            slug    = item.get("slug") or item.get("id") or ""
                            url     = f"{BASE_URL}/fr/missions/{slug}" if slug else ""
                            desc    = (item.get("description") or item.get("summary") or "")[:500]
                            tjm     = str(item.get("tjm") or item.get("daily_rate") or "")
                            if title and url:
                                jobs.append({
                                    "title":       title,
                                    "description": desc,
                                    "url":         url,
                                    "budget_raw":  f"{tjm}€/j" if tjm else "",
                                    "source":      "cremedelacreme",
                                })
                        if jobs:
                            print(f"  ✅ [CrèmeDeLaCrème] {len(jobs)} missions (__NEXT_DATA__)")
                            return jobs
            except Exception:
                pass

        # Fallback scraping HTML classique
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

                desc_el  = _first(card, _DESC_SELECTORS)
                desc     = desc_el.get_text(strip=True)[:500] if desc_el else ""

                tjm_el   = _first(card, _TJM_SELECTORS)
                tjm      = tjm_el.get_text(strip=True) if tjm_el else ""

                tech_el  = _first(card, _TECH_SELECTORS)
                if not desc and tech_el:
                    desc = tech_el.get_text(strip=True)[:500]

                if title and link:
                    jobs.append({
                        "title":       title,
                        "description": desc,
                        "url":         link,
                        "budget_raw":  tjm,
                        "source":      "cremedelacreme",
                    })
            except Exception as exc:
                print(f"  ⚠️  [CrèmeDeLaCrème] card: {exc}")

        await asyncio.sleep(settings.REQUEST_DELAY)

    except requests.RequestException as exc:
        print(f"  ❌ [CrèmeDeLaCrème] Erreur réseau: {exc}")

    print(f"  ✅ [CrèmeDeLaCrème] {len(jobs)} missions trouvées")
    return jobs
