# =============================================================
# sources/toptal.py — scraper Toptal (jobs board public)
# =============================================================
#
# Toptal est une plateforme premium (top 3% des freelances).
# Elle expose un jobboard public HTML à :
#   https://www.toptal.com/developers/blog (articles + jobs)
#   https://www.toptal.com/jobs  (liste des postes ouverts)
#
# Toptal publie des offres de missions pour clients cherchant
# des experts. On scrape la liste publique des jobs ouverts.
# =============================================================

import asyncio
import requests
from bs4 import BeautifulSoup
from config.settings import settings

BASE_URL = "https://www.toptal.com"
LIST_URL = f"{BASE_URL}/jobs"
HEADERS  = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_CARD_SELECTORS  = [
    ".job-listing", ".job-item", "[class*='job-listing']",
    "article.job", ".opening", "[class*='opening']",
    ".jobs-list li", "li[class*='job']", "article",
]
_TITLE_SELECTORS = [
    "h2 a", "h3 a", ".job-title a", ".opening-title a",
    "h2", "h3", ".title",
]
_DESC_SELECTORS  = [
    ".job-description", ".description", ".opening-description",
    "p.desc", "p",
]
_SKILL_SELECTORS = [
    ".skills", ".tags", "[class*='skill']", "[class*='tag']",
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


async def get_toptal_jobs() -> list:
    print("🕷️  [Toptal] Scraping en cours...")
    jobs = []

    try:
        resp = requests.get(LIST_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        cards = []
        for sel in _CARD_SELECTORS:
            cards = soup.select(sel)
            if len(cards) >= 2:
                break

        # Fallback : cherche toutes les <a> pointant vers /jobs/
        if not cards:
            links = soup.select("a[href*='/jobs/'], a[href*='/freelance-']")
            for lnk in links[:20]:
                title = lnk.get_text(strip=True)
                href  = _abs(lnk.get("href", ""))
                if title and href and len(title) > 8:
                    jobs.append({
                        "title":       title,
                        "description": "",
                        "url":         href,
                        "budget_raw":  "",
                        "source":      "toptal",
                    })
            await asyncio.sleep(settings.REQUEST_DELAY)
            print(f"  ✅ [Toptal] {len(jobs)} missions (fallback liens)")
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

                desc_el   = _first(card, _DESC_SELECTORS)
                desc      = desc_el.get_text(strip=True)[:500] if desc_el else ""

                skills_el = _first(card, _SKILL_SELECTORS)
                skills    = skills_el.get_text(strip=True) if skills_el else ""

                if not desc and skills:
                    desc = skills

                if title and link:
                    jobs.append({
                        "title":       title,
                        "description": desc,
                        "url":         link,
                        "budget_raw":  "",
                        "source":      "toptal",
                    })
            except Exception as exc:
                print(f"  ⚠️  [Toptal] card: {exc}")

        await asyncio.sleep(settings.REQUEST_DELAY)

    except requests.RequestException as exc:
        print(f"  ❌ [Toptal] réseau: {exc}")

    print(f"  ✅ [Toptal] {len(jobs)} missions trouvées")
    return jobs
