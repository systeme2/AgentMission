# =============================================================
# sources/indeed_fr.py — scraper Indeed France (RSS)
# =============================================================
#
# Indeed expose des flux RSS publics pour toutes les recherches.
# On scrape plusieurs requêtes ciblées "freelance" + tech FR.
#
# Format RSS : https://fr.indeed.com/rss?q=QUERY&l=France&sort=date
# =============================================================

import asyncio
import re
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
from config.settings import settings
from sources.utils import async_fetch

BASE_URL = "https://fr.indeed.com"
HEADERS  = {
    "User-Agent": "MissionAgentBot/1.0 (personal freelance tracker)",
    "Accept":     "application/rss+xml, application/xml, text/xml, */*",
}

_RSS_QUERIES = [
    "freelance+développeur+web",
    "freelance+wordpress",
    "mission+freelance+web",
    "prestataire+développeur",
]


def _clean_html(text: str) -> str:
    try:
        return BeautifulSoup(text or "", "html.parser").get_text()[:500]
    except Exception:
        return re.sub(r"<[^>]+>", " ", text or "")[:500]


async def get_indeed_fr_jobs() -> list:
    print("🕷️  [Indeed FR] Scraping RSS en cours...")
    jobs: list = []
    seen_urls: set = set()

    for query in _RSS_QUERIES[:2]:  # 2 requêtes pour limiter les appels
        try:
            rss_url = f"{BASE_URL}/rss?q={query}&l=France&sort=date&limit=15"
            resp    = await async_fetch(rss_url, headers=HEADERS, timeout=20)
            resp.raise_for_status()

            root  = ET.fromstring(resp.content)
            items = root.findall(".//item")

            for item in items:
                title = (item.findtext("title") or "").strip()
                link  = (item.findtext("link")  or "").strip()
                desc  = _clean_html(item.findtext("description") or "")

                if not title or not link or link in seen_urls:
                    continue

                # Filtre : garder seulement les offres avec des mots-clés freelance/mission
                text_lower = (title + " " + desc).lower()
                if not any(kw in text_lower for kw in ["freelance", "mission", "prestataire", "indépendant", "contrat"]):
                    continue

                seen_urls.add(link)
                jobs.append({
                    "title":       title,
                    "description": desc,
                    "url":         link,
                    "budget_raw":  "",
                    "source":      "indeed.fr",
                })

            await asyncio.sleep(settings.REQUEST_DELAY)

        except ET.ParseError as exc:
            print(f"  ⚠️  [Indeed FR] XML invalide: {exc}")
        except Exception as exc:
            print(f"  ❌ [Indeed FR] {exc}")

    print(f"  ✅ [Indeed FR] {len(jobs)} missions trouvées")
    return jobs
