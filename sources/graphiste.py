# =============================================================
# sources/graphiste.py — Graphiste.com (section commanditaires)
# =============================================================
#
# Graphiste.com est une plateforme française de mise en relation
# entre donneurs d'ordre (commanditaires) et graphistes/devs web.
# La section "briefs" contient des demandes de création de site,
# refonte, identité visuelle, SEO, e-commerce.
#
# URL : https://www.graphiste.com/briefs
# =============================================================

import asyncio
import json
import requests
from bs4 import BeautifulSoup
from config.settings import settings
from sources.utils import async_fetch

BASE_URL = "https://www.graphiste.com"

LIST_URLS = [
    f"{BASE_URL}/briefs",
    f"{BASE_URL}/briefs?category=site-internet",
    f"{BASE_URL}/briefs?category=referencement-seo",
    f"{BASE_URL}/briefs?category=e-commerce",
]

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer":         BASE_URL,
}

_CARD_SELECTORS = [
    ".brief-card",        "[class*='brief-card']",
    ".project-card",      "[class*='project-card']",
    ".mission-card",      "[class*='mission']",
    "article.brief",      "article",
    "[class*='listing']",
]
_TITLE_SELECTORS = ["h2 a", "h3 a", ".brief-title a", ".title a", "h2", "h3", ".brief-title"]
_DESC_SELECTORS  = [".brief-description", ".description", ".excerpt", ".resume", "p"]
_BUDGET_SELECTORS = [".budget", "[class*='budget']", ".price", "[class*='price']", ".budget-range"]

_RELEVANT_KEYWORDS = [
    "wordpress", "shopify", "création site", "site internet", "site web",
    "refonte", "e-commerce", "woocommerce", "landing page", "seo",
    "référencement", "développeur web", "webmaster", "prestashop",
    "vitrine", "boutique", "intégrateur", "web design", "ux",
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
    """Extrait les briefs depuis __NEXT_DATA__ si disponible."""
    jobs = []
    script = soup.find("script", {"id": "__NEXT_DATA__"})
    if not script or not script.string:
        return jobs

    try:
        payload    = json.loads(script.string)
        page_props = payload.get("props", {}).get("pageProps", {})

        for key in ("briefs", "projects", "missions", "data", "items", "results"):
            items = page_props.get(key, [])
            if not isinstance(items, list) or not items:
                continue

            for item in items[:30]:
                if not isinstance(item, dict):
                    continue
                title  = (item.get("title") or item.get("name") or item.get("subject") or "").strip()
                slug   = item.get("slug") or item.get("id") or ""
                url    = item.get("url") or item.get("link") or ""
                if not url and slug:
                    url = f"{BASE_URL}/briefs/{slug}"
                desc   = (item.get("description") or item.get("content") or item.get("summary") or "")[:500]
                budget = str(item.get("budget") or item.get("price") or item.get("remuneration") or "")

                if title and url and _is_relevant(title + " " + desc):
                    jobs.append({
                        "title":       title,
                        "description": desc,
                        "url":         _abs(url),
                        "budget_raw":  budget,
                        "source":      "graphiste",
                    })

            if jobs:
                break

    except (json.JSONDecodeError, AttributeError, KeyError):
        pass

    return jobs


async def get_graphiste_jobs() -> list:
    print("🕷️  [Graphiste] Scraping en cours...")
    jobs: list = []
    seen_urls: set = set()

    for page_url in LIST_URLS[:3]:
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
                break

            # Fallback HTML scraping
            cards = []
            for sel in _CARD_SELECTORS:
                cards = soup.select(sel)
                if len(cards) >= 3:
                    break

            # Fallback : liens directs vers les briefs
            if not cards:
                for a in soup.select("a[href*='/briefs/']")[:20]:
                    title = a.get_text(strip=True)
                    href  = _abs(a.get("href", ""))
                    if title and href and href not in seen_urls and len(title) > 8:
                        if _is_relevant(title):
                            seen_urls.add(href)
                            jobs.append({
                                "title":       title,
                                "description": "",
                                "url":         href,
                                "budget_raw":  "",
                                "source":      "graphiste",
                            })

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
                        "source":      "graphiste",
                    })
                except Exception as exc:
                    print(f"  ⚠️  [Graphiste] card: {exc}")

            await asyncio.sleep(settings.REQUEST_DELAY)

        except requests.RequestException as exc:
            print(f"  ❌ [Graphiste] {page_url}: {exc}")
        except Exception as exc:
            print(f"  ⚠️  [Graphiste] parsing: {exc}")

    print(f"  ✅ [Graphiste] {len(jobs)} missions trouvées")
    return jobs
