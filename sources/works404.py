# =============================================================
# sources/works404.py — scraper 404Works
# =============================================================
#
# 404Works est une plateforme 100 % française centrée web/UX,
# sans commission (abonnement mensuel côté freelance).
# Elle expose un jobboard HTML standard avec pagination.
# =============================================================

import asyncio
import requests
from bs4 import BeautifulSoup
from config.settings import settings
from sources.utils import async_fetch

BASE_URL = "https://404works.com"
LIST_URL = f"{BASE_URL}/missions"
HEADERS  = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

_PROJECT_SELECTORS = [
    ".job-item", ".mission-item", ".offer-card",
    "article.job", "article", ".job-listing",
]
_TITLE_SELECTORS   = ["h2 a", "h3 a", ".job-title a", "h2", "h3", ".title"]
_DESC_SELECTORS    = [".job-description", ".description", ".excerpt", "p"]
_BUDGET_SELECTORS  = [".salary", ".budget", "[class*='salary']", "[class*='budget']"]


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


async def get_404works_jobs() -> list:
    print("🕷️  [404Works] Scraping en cours...")
    jobs = []

    try:
        resp = await async_fetch(LIST_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        projects = []
        for sel in _PROJECT_SELECTORS:
            projects = soup.select(sel)
            if projects:
                break

        # Fallback générique : toute card/section avec un <a> contenant "mission"
        if not projects:
            projects = soup.select("[class*='card'], [class*='item'], [class*='offer']")

        for proj in projects:
            try:
                title_el = _first(proj, _TITLE_SELECTORS)
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if len(title) < 5:
                    continue

                # Lien
                if title_el.name == "a":
                    href = title_el.get("href", "")
                else:
                    a = proj.select_one("a")
                    href = a.get("href", "") if a else ""
                link = _abs(href)

                desc_el = _first(proj, _DESC_SELECTORS)
                desc    = desc_el.get_text(strip=True)[:500] if desc_el else ""

                budget_el = _first(proj, _BUDGET_SELECTORS)
                budget    = budget_el.get_text(strip=True) if budget_el else ""

                if title and link:
                    jobs.append({
                        "title":       title,
                        "description": desc,
                        "url":         link,
                        "budget_raw":  budget,
                        "source":      "404works",
                    })
            except Exception as exc:
                print(f"  ⚠️  [404Works] parsing: {exc}")

        await asyncio.sleep(settings.REQUEST_DELAY)

    except requests.RequestException as exc:
        print(f"  ❌ [404Works] Erreur réseau: {exc}")

    print(f"  ✅ [404Works] {len(jobs)} missions trouvées")
    return jobs
