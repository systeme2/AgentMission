# =============================================================
# sources/wellfound.py — Wellfound (ex-AngelList) startups FR
# =============================================================
#
# Wellfound est la plateforme de référence pour les startups.
# Les startups qui se lancent → besoin de devs freelance.
#
# Stratégie :
#   1. API de recherche de jobs (filtre France + type contract)
#   2. Fallback : scraping HTML de la page jobs
#
# URL API : https://wellfound.com/jobs (graphQL)
# Fallback : https://wellfound.com/jobs?country_id=FR
# =============================================================

import asyncio
import json
import requests
from bs4 import BeautifulSoup
from config.settings import settings
from sources.utils import async_fetch

BASE_URL   = "https://wellfound.com"
SEARCH_URL = f"{BASE_URL}/jobs"

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Referer":         BASE_URL,
}

_CARD_SELECTORS  = [
    "[class*='job-listing']", "[class*='JobListing']",
    "[class*='startup-job']", "[class*='StartupJob']",
    "div[class*='listing']", "article",
]
_TITLE_SELECTORS = ["h2 a", "h3 a", "a[class*='title']", "a[class*='job-name']", "h2", "h3"]
_DESC_SELECTORS  = ["p[class*='description']", "div[class*='description']", "p"]
_COMP_SELECTORS  = ["[class*='startup-name']", "[class*='company']", "h4", "span[class*='name']"]


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


async def get_wellfound_jobs() -> list:
    print("🕷️  [Wellfound] Scraping en cours...")
    jobs: list = []
    seen_urls: set = set()

    # Paramètres de recherche : France + contrats courts / remote
    search_params = [
        {"country_id": "FR", "job_type": "contract"},
        {"country_id": "FR", "role_type": "freelance"},
        {"location_id": "paris", "job_type": "contract"},
    ]

    for params in search_params[:1]:  # 1 requête pour limiter
        try:
            resp = await async_fetch(SEARCH_URL, headers=HEADERS, params=params, timeout=20)
            if resp.status_code in (403, 429):
                print(f"  ⚠️  [Wellfound] Bloqué (HTTP {resp.status_code})")
                break
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Tentative __NEXT_DATA__ (Next.js)
            next_data = soup.find("script", {"id": "__NEXT_DATA__"})
            if next_data and next_data.string:
                try:
                    payload = json.loads(next_data.string)
                    page_props = payload.get("props", {}).get("pageProps", {})
                    for key in ("jobs", "jobListings", "listings", "results", "data"):
                        items = page_props.get(key, [])
                        if isinstance(items, list) and items:
                            for item in items[:20]:
                                if not isinstance(item, dict):
                                    continue
                                title   = (item.get("title") or item.get("role") or "").strip()
                                company = ""
                                startup = item.get("startup") or item.get("company") or {}
                                if isinstance(startup, dict):
                                    company = startup.get("name", "")
                                slug = item.get("id") or item.get("slug") or ""
                                url  = f"{BASE_URL}/jobs/{slug}" if slug else ""
                                if not url:
                                    url = item.get("url") or item.get("applyUrl") or ""
                                desc = (item.get("description") or "")[:500]

                                if title and url and url not in seen_urls:
                                    seen_urls.add(url)
                                    full_title = f"{title} @ {company}".strip(" @") if company else title
                                    jobs.append({
                                        "title":       full_title,
                                        "description": desc,
                                        "url":         url,
                                        "budget_raw":  str(item.get("salary") or ""),
                                        "source":      "wellfound",
                                    })
                            if jobs:
                                break
                except Exception:
                    pass

            # Fallback HTML si Next.js vide
            if not jobs:
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

                        comp_el = _first(card, _COMP_SELECTORS)
                        company = comp_el.get_text(strip=True) if comp_el else ""
                        desc_el = _first(card, _DESC_SELECTORS)
                        desc    = desc_el.get_text(strip=True)[:500] if desc_el else ""

                        seen_urls.add(link)
                        full_title = f"{title} @ {company}".strip(" @") if company else title
                        jobs.append({
                            "title":       full_title,
                            "description": desc,
                            "url":         link,
                            "budget_raw":  "",
                            "source":      "wellfound",
                        })
                    except Exception as exc:
                        print(f"  ⚠️  [Wellfound] card: {exc}")

            await asyncio.sleep(settings.REQUEST_DELAY)

        except requests.RequestException as exc:
            print(f"  ❌ [Wellfound] réseau: {exc}")
        except Exception as exc:
            print(f"  ⚠️  [Wellfound] parsing: {exc}")

    print(f"  ✅ [Wellfound] {len(jobs)} missions trouvées")
    return jobs
