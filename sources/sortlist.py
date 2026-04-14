# =============================================================
# sources/sortlist.py — Sortlist.fr
# =============================================================
#
# Sortlist est une plateforme de mise en relation entre clients
# et agences/freelances. Beaucoup de missions web, création de
# site, refonte, SEO, e-commerce pour des PME françaises.
#
# URL : https://www.sortlist.fr/s/creation-de-site-internet
# =============================================================

import asyncio
import json
import requests
from bs4 import BeautifulSoup
from config.settings import settings
from sources.utils import async_fetch

BASE_URL = "https://www.sortlist.fr"

# Pages de projets publiés sur Sortlist
PROJECT_URLS = [
    f"{BASE_URL}/projects/web-design",
    f"{BASE_URL}/projects/creation-de-site-internet",
    f"{BASE_URL}/projects/referencement-seo",
    f"{BASE_URL}/projects/e-commerce",
    f"{BASE_URL}/projects/wordpress",
    f"{BASE_URL}/projects",
]

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer":         BASE_URL,
}

_CARD_SELECTORS = [
    "[class*='project-card']", "[class*='ProjectCard']",
    "[class*='brief-card']",   "[class*='BriefCard']",
    "article.project",         "article",
    "[class*='mission']",      "[class*='offer']",
]
_TITLE_SELECTORS = ["h2 a", "h3 a", ".title a", "h2", "h3", ".project-title"]
_DESC_SELECTORS  = [".description", ".excerpt", ".summary", "p.brief", "p"]
_BUDGET_SELECTORS = [".budget", "[class*='budget']", ".price", "[class*='price']"]

_RELEVANT_KEYWORDS = [
    "wordpress", "shopify", "création site", "site internet", "site web",
    "refonte", "e-commerce", "woocommerce", "landing page", "seo",
    "référencement", "développeur web", "webmaster", "prestashop",
    "vitrine", "boutique", "intégrateur",
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


def _is_relevant(text: str) -> bool:
    low = text.lower()
    return any(kw in low for kw in _RELEVANT_KEYWORDS)


def _parse_next_data(soup: BeautifulSoup) -> list:
    """Extrait les projets depuis __NEXT_DATA__ si disponible."""
    jobs = []
    script = soup.find("script", {"id": "__NEXT_DATA__"})
    if not script or not script.string:
        return jobs

    try:
        payload    = json.loads(script.string)
        page_props = payload.get("props", {}).get("pageProps", {})

        for key in ("projects", "briefs", "missions", "data", "items", "results"):
            items = page_props.get(key, [])
            if not isinstance(items, list) or not items:
                continue

            for item in items[:30]:
                if not isinstance(item, dict):
                    continue
                title  = (item.get("title") or item.get("name") or "").strip()
                slug   = item.get("slug") or item.get("id") or ""
                url    = item.get("url") or item.get("link") or ""
                if not url and slug:
                    url = f"{BASE_URL}/projects/{slug}"
                desc   = (item.get("description") or item.get("summary") or item.get("brief") or "")[:500]
                budget = str(item.get("budget") or item.get("price") or "")

                if title and url and _is_relevant(title + " " + desc):
                    jobs.append({
                        "title":       title,
                        "description": desc,
                        "url":         _abs(url),
                        "budget_raw":  budget,
                        "source":      "sortlist",
                    })

            if jobs:
                break

    except (json.JSONDecodeError, AttributeError, KeyError):
        pass

    return jobs


async def get_sortlist_jobs() -> list:
    print("🕷️  [Sortlist] Scraping en cours...")
    jobs: list = []
    seen_urls: set = set()

    for page_url in PROJECT_URLS[:3]:
        try:
            resp = await async_fetch(page_url, headers=HEADERS, timeout=20)
            if resp.status_code in (404, 403, 503):
                continue
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Tentative __NEXT_DATA__
            next_jobs = _parse_next_data(soup)
            for job in next_jobs:
                if job["url"] not in seen_urls:
                    seen_urls.add(job["url"])
                    jobs.append(job)

            if jobs:
                break  # On arrête à la première URL productive

            # Fallback HTML scraping
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

                    desc_el   = _first(card, _DESC_SELECTORS)
                    desc      = desc_el.get_text(strip=True)[:500] if desc_el else ""
                    budget_el = _first(card, _BUDGET_SELECTORS)
                    budget    = budget_el.get_text(strip=True) if budget_el else ""

                    if not _is_relevant(title + " " + desc):
                        continue

                    seen_urls.add(link)
                    jobs.append({
                        "title":       title,
                        "description": desc,
                        "url":         link,
                        "budget_raw":  budget,
                        "source":      "sortlist",
                    })
                except Exception as exc:
                    print(f"  ⚠️  [Sortlist] card: {exc}")

            await asyncio.sleep(settings.REQUEST_DELAY)

        except requests.RequestException as exc:
            print(f"  ❌ [Sortlist] {page_url}: {exc}")
        except Exception as exc:
            print(f"  ⚠️  [Sortlist] parsing: {exc}")

    print(f"  ✅ [Sortlist] {len(jobs)} missions trouvées")
    return jobs
