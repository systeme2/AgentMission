# =============================================================
# sources/freelancerepublik.py — FreelanceRepublik
# =============================================================
#
# FreelanceRepublik est une plateforme FR spécialisée IT/web,
# sans commission côté freelance (abonnement mensuel).
# Les clients sont principalement des PME et ETI françaises.
# Beaucoup de missions WordPress, Shopify, refonte, SEO.
#
# URL : https://www.freelancerepublik.com/missions
# =============================================================

import asyncio
import json
import requests
from bs4 import BeautifulSoup
from config.settings import settings
from sources.utils import async_fetch

BASE_URL  = "https://www.freelancerepublik.com"
LIST_URL  = f"{BASE_URL}/missions"
HEADERS   = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer":         BASE_URL,
}

# Catégories pertinentes sur FreelanceRepublik
CATEGORY_URLS = [
    f"{BASE_URL}/missions?category=developpement-web",
    f"{BASE_URL}/missions?category=creation-site-internet",
    f"{BASE_URL}/missions?category=wordpress",
    f"{BASE_URL}/missions?category=ecommerce",
    f"{BASE_URL}/missions?category=seo-referencement",
    f"{BASE_URL}/missions",
]

_CARD_SELECTORS  = [
    ".mission-card", "[class*='mission-card']",
    ".job-card",     "[class*='job-card']",
    "article.mission", "article",
    "[class*='mission-item']", "[class*='offer-item']",
]
_TITLE_SELECTORS = ["h2 a", "h3 a", ".mission-title a", ".title a", "h2", "h3"]
_DESC_SELECTORS  = [".mission-description", ".description", ".excerpt", "p.desc", "p"]
_TJM_SELECTORS   = [".tjm", ".budget", "[class*='tjm']", "[class*='budget']", ".price"]
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


async def get_freelancerepublik_jobs() -> list:
    print("🕷️  [FreelanceRepublik] Scraping en cours...")
    jobs: list = []
    seen_urls: set = set()

    # On scrape 2 URLs max : la principale + une catégorie ciblée
    for page_url in CATEGORY_URLS[:2]:
        try:
            resp = await async_fetch(page_url, headers=HEADERS, timeout=20)
            if resp.status_code in (404, 403, 503):
                continue
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Tentative __NEXT_DATA__ (Next.js / Nuxt)
            for script_id in ["__NEXT_DATA__", "__NUXT_DATA__"]:
                script = soup.find("script", {"id": script_id})
                if script and script.string:
                    try:
                        payload    = json.loads(script.string)
                        page_props = payload.get("props", {}).get("pageProps", {})
                        for key in ("missions", "jobs", "offers", "data", "results"):
                            items = page_props.get(key, [])
                            if isinstance(items, list) and items:
                                for item in items[:25]:
                                    if not isinstance(item, dict):
                                        continue
                                    title  = (item.get("title") or item.get("name") or "").strip()
                                    slug   = item.get("slug") or item.get("id") or ""
                                    url    = item.get("url") or (f"{BASE_URL}/missions/{slug}" if slug else "")
                                    desc   = (item.get("description") or item.get("summary") or "")[:500]
                                    budget = str(item.get("tjm") or item.get("budget") or item.get("salary") or "")
                                    if title and url and url not in seen_urls:
                                        seen_urls.add(url)
                                        jobs.append({
                                            "title":       title,
                                            "description": desc,
                                            "url":         _abs(url),
                                            "budget_raw":  budget,
                                            "source":      "freelancerepublik",
                                        })
                                if jobs:
                                    break
                    except Exception:
                        pass
                if jobs:
                    break

            # Fallback HTML classique
            if not jobs:
                cards = []
                for sel in _CARD_SELECTORS:
                    cards = soup.select(sel)
                    if len(cards) >= 3:
                        break

                for card in cards[:25]:
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

                        desc_el  = _first(card, _DESC_SELECTORS)
                        desc     = desc_el.get_text(strip=True)[:500] if desc_el else ""

                        tjm_el   = _first(card, _TJM_SELECTORS)
                        tjm      = tjm_el.get_text(strip=True) if tjm_el else ""

                        tech_el  = _first(card, _TECH_SELECTORS)
                        if not desc and tech_el:
                            desc = tech_el.get_text(strip=True)[:300]

                        seen_urls.add(link)
                        jobs.append({
                            "title":       title,
                            "description": desc,
                            "url":         link,
                            "budget_raw":  tjm,
                            "source":      "freelancerepublik",
                        })
                    except Exception as exc:
                        print(f"  ⚠️  [FreelanceRepublik] card: {exc}")

            await asyncio.sleep(settings.REQUEST_DELAY)

        except requests.RequestException as exc:
            print(f"  ❌ [FreelanceRepublik] {page_url}: {exc}")
        except Exception as exc:
            print(f"  ⚠️  [FreelanceRepublik] parsing: {exc}")

    print(f"  ✅ [FreelanceRepublik] {len(jobs)} missions trouvées")
    return jobs
