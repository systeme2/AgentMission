# =============================================================
# sources/collective_work.py — scraper Collective.work
# =============================================================
#
# Collective.work est une plateforme FR sans commission,
# orientée collaboration long terme (solo ou collectifs).
# Elle expose un jobboard public avec des offres de missions.
#
# Deux endpoints utiles :
#   - /jobs          → liste des offres ouvertes
#   - /api/jobs      → JSON si disponible (tentative first)
# =============================================================

import asyncio
import json
import requests
from bs4 import BeautifulSoup
from config.settings import settings

BASE_URL  = "https://collective.work"
API_URL   = f"{BASE_URL}/api/jobs"
LIST_URL  = f"{BASE_URL}/jobs"
HEADERS   = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Accept":          "application/json, text/html, */*",
}

_CARD_SELECTORS   = [
    ".job-offer", ".job-card", ".offer-item", "[class*='job']",
    "article", "[class*='offer']", "[class*='mission']",
]
_TITLE_SELECTORS  = ["h2 a", "h3 a", ".job-title a", "h2", "h3", ".title"]
_DESC_SELECTORS   = [".description", ".job-description", ".summary", "p.desc", "p"]
_BUDGET_SELECTORS = [".salary", ".budget", ".tjm", "[class*='salary']", "[class*='budget']"]
_COMPANY_SELECTORS= [".company", ".employer", "[class*='company']", ".client"]


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


def _parse_json_response(data) -> list:
    """Tente d'extraire des jobs depuis une réponse JSON."""
    jobs = []
    items = []

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        # Cherche une clé qui ressemble à une liste de jobs
        for key in ("jobs", "offers", "results", "data", "items"):
            if key in data and isinstance(data[key], list):
                items = data[key]
                break

    for item in items[:30]:
        if not isinstance(item, dict):
            continue
        title = (
            item.get("title") or item.get("name") or
            item.get("job_title") or ""
        )
        raw_url = item.get("url") or item.get("link") or ""
        if raw_url.startswith("http"):
            url = raw_url
        elif raw_url.startswith("/"):
            url = BASE_URL + raw_url
        else:
            slug = item.get("slug") or item.get("id") or ""
            url = f"{BASE_URL}/jobs/{slug}" if slug else ""

        desc = (
            item.get("description") or item.get("summary") or
            item.get("excerpt") or ""
        )[:500]

        budget = str(
            item.get("salary") or item.get("budget") or
            item.get("tjm") or ""
        )
        company = str(
            item.get("company") or item.get("employer") or
            item.get("client") or ""
        )

        if title and url:
            jobs.append({
                "title":       f"{title} @ {company}".strip(" @") if company else title,
                "description": desc,
                "url":         url,
                "budget_raw":  budget,
                "source":      "collective.work",
            })
    return jobs


async def get_collective_work_jobs() -> list:
    print("🕷️  [Collective.work] Scraping en cours...")
    jobs = []

    # ── Tentative 1 : API JSON ───────────────────────────────
    try:
        resp = requests.get(
            API_URL,
            headers={**HEADERS, "Accept": "application/json"},
            timeout=15,
        )
        if resp.status_code == 200 and "application/json" in resp.headers.get("Content-Type", ""):
            data = resp.json()
            jobs = _parse_json_response(data)
            if jobs:
                print(f"  ✅ [Collective.work] {len(jobs)} missions (API JSON)")
                await asyncio.sleep(settings.REQUEST_DELAY)
                return jobs
    except Exception:
        pass

    # ── Tentative 2 : scraping HTML ──────────────────────────
    try:
        resp = requests.get(LIST_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()

        # Vérifier si JSON embarqué (Next.js __NEXT_DATA__)
        soup = BeautifulSoup(resp.text, "html.parser")
        next_data = soup.find("script", {"id": "__NEXT_DATA__"})
        if next_data:
            try:
                payload = json.loads(next_data.string)
                # Naviguer dans l'arbre pageProps
                page_props = (
                    payload.get("props", {})
                           .get("pageProps", {})
                )
                for key in ("jobs", "offers", "missions", "data"):
                    if key in page_props:
                        jobs = _parse_json_response(page_props[key])
                        if jobs:
                            print(f"  ✅ [Collective.work] {len(jobs)} missions (__NEXT_DATA__)")
                            await asyncio.sleep(settings.REQUEST_DELAY)
                            return jobs
            except Exception:
                pass

        # Scraping HTML classique
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

                if title_el.name == "a":
                    href = title_el.get("href", "")
                else:
                    a = card.select_one("a")
                    href = a.get("href", "") if a else ""
                link = _abs(href)

                desc_el    = _first(card, _DESC_SELECTORS)
                desc       = desc_el.get_text(strip=True)[:500] if desc_el else ""

                budget_el  = _first(card, _BUDGET_SELECTORS)
                budget     = budget_el.get_text(strip=True) if budget_el else ""

                company_el = _first(card, _COMPANY_SELECTORS)
                company    = company_el.get_text(strip=True) if company_el else ""

                if title and link:
                    jobs.append({
                        "title":       f"{title} @ {company}".strip(" @") if company else title,
                        "description": desc,
                        "url":         link,
                        "budget_raw":  budget,
                        "source":      "collective.work",
                    })
            except Exception as exc:
                print(f"  ⚠️  [Collective.work] parsing: {exc}")

        await asyncio.sleep(settings.REQUEST_DELAY)

    except requests.RequestException as exc:
        print(f"  ❌ [Collective.work] Erreur réseau: {exc}")

    print(f"  ✅ [Collective.work] {len(jobs)} missions trouvées")
    return jobs
