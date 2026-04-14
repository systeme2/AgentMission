# =============================================================
# sources/freelance_com.py — scraper Freelance.com
# =============================================================
#
# Freelance.com est l'un des plus anciens acteurs français (2000).
# Il expose une page de projets en HTML statique + pagination.
# Stratégie : scraper la liste des projets récents, extraire
# titre / description / budget / lien pour chaque carte projet.
# =============================================================

import asyncio
import re
import requests
from bs4 import BeautifulSoup
from config.settings import settings
from sources.utils import async_fetch

BASE_URL   = "https://www.freelance.com"
LIST_URL   = f"{BASE_URL}/freelances/missions.php"
HEADERS    = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Sélecteurs CSS — plusieurs alternatives pour absorber les changements de markup
_PROJECT_SELECTORS = [
    "article.project",
    ".mission-item",
    ".project-card",
    "[class*='mission']",
    "article",
]
_TITLE_SELECTORS   = ["h2 a", "h3 a", ".title a", "a.mission-title", "h2", "h3"]
_DESC_SELECTORS    = [".description", ".summary", "p.mission-desc", "p"]
_BUDGET_SELECTORS  = [".budget", "[class*='budget']", "[class*='prix']", "[class*='tarif']"]
_LINK_ATTRS        = ["href"]


def _first(soup_el, selectors):
    """Retourne le premier élément trouvé parmi une liste de sélecteurs CSS."""
    for sel in selectors:
        el = soup_el.select_one(sel)
        if el:
            return el
    return None


def _make_absolute(href: str) -> str:
    if not href:
        return ""
    if href.startswith("http"):
        return href
    return BASE_URL + ("" if href.startswith("/") else "/") + href


async def get_freelance_com_jobs() -> list:
    print("🕷️  [Freelance.com] Scraping en cours...")
    jobs = []

    try:
        resp = await async_fetch(LIST_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Trouver les blocs projets
        projects = []
        for sel in _PROJECT_SELECTORS:
            projects = soup.select(sel)
            if projects:
                break

        # Fallback : chercher les liens qui pointent vers des pages mission
        if not projects:
            links = soup.select("a[href*='mission'], a[href*='projet'], a[href*='project']")
            for lnk in links[:30]:
                title = lnk.get_text(strip=True)
                href  = _make_absolute(lnk.get("href", ""))
                if title and href and len(title) > 8:
                    jobs.append({
                        "title":       title,
                        "description": "",
                        "url":         href,
                        "budget_raw":  "",
                        "source":      "freelance.com",
                    })
            await asyncio.sleep(settings.REQUEST_DELAY)
            print(f"  ✅ [Freelance.com] {len(jobs)} missions (fallback liens)")
            return jobs

        for proj in projects:
            try:
                title_el = _first(proj, _TITLE_SELECTORS)
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)

                # Lien — d'abord dans le titre, sinon premier <a>
                href = ""
                if title_el.name == "a":
                    href = title_el.get("href", "")
                else:
                    a = proj.select_one("a")
                    href = a.get("href", "") if a else ""
                link = _make_absolute(href)

                desc_el  = _first(proj, _DESC_SELECTORS)
                desc     = desc_el.get_text(strip=True)[:500] if desc_el else ""

                budget_el = _first(proj, _BUDGET_SELECTORS)
                budget    = budget_el.get_text(strip=True) if budget_el else ""

                if title and link:
                    jobs.append({
                        "title":       title,
                        "description": desc,
                        "url":         link,
                        "budget_raw":  budget,
                        "source":      "freelance.com",
                    })
            except Exception as exc:
                print(f"  ⚠️  [Freelance.com] parsing: {exc}")

        await asyncio.sleep(settings.REQUEST_DELAY)

    except requests.RequestException as exc:
        print(f"  ❌ [Freelance.com] Erreur réseau: {exc}")

    print(f"  ✅ [Freelance.com] {len(jobs)} missions trouvées")
    return jobs
