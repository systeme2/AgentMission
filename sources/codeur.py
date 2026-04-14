# =============================================================
# sources/codeur.py — scraper Codeur.com
# =============================================================

import asyncio
import time
import requests
from bs4 import BeautifulSoup
from config.settings import settings
from sources.utils import async_fetch

BASE_URL = "https://www.codeur.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9",
}


async def get_codeur_jobs() -> list:
    print("🕷️  [Codeur] Scraping en cours...")
    jobs = []

    try:
        url = f"{BASE_URL}/projects"
        resp = await async_fetch(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Codeur utilise des classes dynamiques — on essaie plusieurs sélecteurs
        projects = (
            soup.select(".project-item") or
            soup.select("[data-project]") or
            soup.select(".project") or
            soup.select("article")
        )

        for p in projects:
            try:
                # Titre
                title_el = (
                    p.select_one(".project-title") or
                    p.select_one("h2") or
                    p.select_one("h3") or
                    p.select_one("a[href*='/projects/']")
                )
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)

                # Lien
                link_el = p.select_one("a[href*='/projects/']") or p.select_one("a")
                if not link_el:
                    continue
                href = link_el.get("href", "")
                link = BASE_URL + href if href.startswith("/") else href

                # Description courte
                desc_el = p.select_one(".project-description") or p.select_one("p")
                description = desc_el.get_text(strip=True)[:500] if desc_el else ""

                # Budget (si disponible)
                budget_el = p.select_one(".budget") or p.select_one("[class*='budget']")
                budget_text = budget_el.get_text(strip=True) if budget_el else ""

                if title and link:
                    jobs.append({
                        "title": title,
                        "description": description,
                        "url": link,
                        "budget_raw": budget_text,
                        "source": "codeur",
                    })
            except Exception as e:
                print(f"  ⚠️  Erreur parsing projet Codeur: {e}")
                continue

        await asyncio.sleep(settings.REQUEST_DELAY)

    except requests.RequestException as e:
        print(f"  ❌ [Codeur] Erreur réseau: {e}")

    print(f"  ✅ [Codeur] {len(jobs)} missions trouvées")
    return jobs
