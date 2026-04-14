# =============================================================
# sources/malt.py — scraper Malt (site JS → Playwright)
# =============================================================
#
# Malt est le leader français avec 700k+ freelances.
# Le site est rendu côté client (React) : BeautifulSoup seul
# ne voit qu'un HTML vide. On utilise Playwright en mode
# headless pour récupérer le DOM complet après exécution JS.
#
# Stratégie :
#   1. Ouvrir la page de recherche de missions
#   2. Attendre le sélecteur d'une card projet
#   3. Extraire titre / description / budget / lien
#   4. Fallback : si Playwright indisponible → requests + BS4
# =============================================================

import asyncio
import re
import requests
from bs4 import BeautifulSoup
from config.settings import settings
from sources.utils import async_fetch

BASE_URL    = "https://www.malt.fr"
SEARCH_URL  = f"{BASE_URL}/s?q=freelance+d%C3%A9veloppeur&jt=freelance"
HEADERS     = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

# Sélecteurs Playwright (valeurs 2024 — à adapter si Malt change son CSS)
_PW_CARD    = "[data-cy='profile-card'], .c-profile-card, .freelancer-card, article[class*='profile']"
_PW_TITLE   = "[data-cy='profile-name'], .c-profile-card__name, h2, h3"
_PW_DESC    = "[data-cy='profile-headline'], .c-profile-card__headline, p"
_PW_PRICE   = "[data-cy='daily-rate'], .c-profile-card__rate, [class*='rate'], [class*='price']"
_PW_LINK    = "a[href*='/profile/'], a[href*='/freelance/']"

# Sélecteurs BeautifulSoup fallback
_BS_CARD    = ["[data-cy='profile-card']", ".c-profile-card", "article", ".profile-card"]
_BS_TITLE   = ["[data-cy='profile-name']", "h2", "h3", ".name"]
_BS_DESC    = ["[data-cy='profile-headline']", "p.headline", "p"]
_BS_PRICE   = ["[data-cy='daily-rate']", "[class*='rate']", "[class*='price']", ".price"]


def _abs(href: str) -> str:
    if not href:
        return ""
    return href if href.startswith("http") else BASE_URL + href


def _first_bs(el, selectors):
    for sel in selectors:
        found = el.select_one(sel)
        if found:
            return found
    return None


async def _scrape_with_playwright() -> list:
    """Scraping JS via Playwright headless Chromium."""
    from playwright.async_api import async_playwright, TimeoutError as PWTimeout

    jobs = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx     = await browser.new_context(
            locale="fr-FR",
            user_agent=HEADERS["User-Agent"],
        )
        page = await ctx.new_page()

        try:
            await page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=30_000)

            # Attendre qu'au moins une card apparaisse
            try:
                await page.wait_for_selector(_PW_CARD, timeout=15_000)
            except PWTimeout:
                print("  ⚠️  [Malt/PW] Aucune card détectée — page peut-être bloquée")

            cards = await page.query_selector_all(_PW_CARD)
            print(f"  [Malt/PW] {len(cards)} cards trouvées")

            for card in cards[:20]:
                try:
                    title_el = await card.query_selector(_PW_TITLE)
                    title    = (await title_el.inner_text()).strip() if title_el else ""
                    if not title or len(title) < 3:
                        continue

                    link_el  = await card.query_selector(_PW_LINK)
                    href     = await link_el.get_attribute("href") if link_el else ""
                    link     = _abs(href)

                    desc_el  = await card.query_selector(_PW_DESC)
                    desc     = (await desc_el.inner_text()).strip()[:500] if desc_el else ""

                    price_el = await card.query_selector(_PW_PRICE)
                    price    = (await price_el.inner_text()).strip() if price_el else ""

                    if title and link:
                        jobs.append({
                            "title":       title,
                            "description": desc,
                            "url":         link,
                            "budget_raw":  price,
                            "source":      "malt",
                        })
                except Exception as exc:
                    print(f"  ⚠️  [Malt/PW] card parsing: {exc}")

        except Exception as exc:
            print(f"  ❌ [Malt/PW] navigation: {exc}")
        finally:
            await browser.close()

    return jobs


async def _scrape_with_requests() -> list:
    """Fallback BeautifulSoup si Playwright non disponible."""
    jobs = []
    try:
        resp = await async_fetch(SEARCH_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        cards = []
        for sel in _BS_CARD:
            cards = soup.select(sel)
            if len(cards) >= 2:
                break

        for card in cards[:20]:
            try:
                title_el = _first_bs(card, _BS_TITLE)
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if len(title) < 3:
                    continue

                a = card.select_one("a")
                href  = a.get("href", "") if a else ""
                link  = _abs(href)

                desc_el = _first_bs(card, _BS_DESC)
                desc    = desc_el.get_text(strip=True)[:500] if desc_el else ""

                price_el = _first_bs(card, _BS_PRICE)
                price    = price_el.get_text(strip=True) if price_el else ""

                if title and link:
                    jobs.append({
                        "title":       title,
                        "description": desc,
                        "url":         link,
                        "budget_raw":  price,
                        "source":      "malt",
                    })
            except Exception as exc:
                print(f"  ⚠️  [Malt/BS] card: {exc}")

    except requests.RequestException as exc:
        print(f"  ❌ [Malt/BS] réseau: {exc}")

    return jobs


async def get_malt_jobs() -> list:
    print("🕷️  [Malt] Scraping en cours...")

    # Tentative Playwright
    try:
        import playwright  # noqa: F401 — vérifie juste la disponibilité
        jobs = await _scrape_with_playwright()
        if jobs:
            await asyncio.sleep(settings.REQUEST_DELAY)
            print(f"  ✅ [Malt] {len(jobs)} missions (Playwright)")
            return jobs
        print("  ⚠️  [Malt] Playwright n'a rien retourné, bascule sur requests")
    except ImportError:
        print("  ℹ️  [Malt] Playwright non installé → fallback requests")
    except Exception as exc:
        print(f"  ⚠️  [Malt] Playwright a planté ({exc}) → fallback requests")

    # Fallback requests — toujours retourner une liste, jamais lever
    try:
        jobs = await _scrape_with_requests()
    except Exception as exc:
        print(f"  ❌ [Malt] fallback requests a échoué: {exc}")
        jobs = []
    await asyncio.sleep(settings.REQUEST_DELAY)
    print(f"  ✅ [Malt] {len(jobs)} missions (requests fallback)")
    return jobs
