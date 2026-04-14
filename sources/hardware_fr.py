# =============================================================
# sources/hardware_fr.py — Forum Hardware.fr (section Emploi)
# =============================================================
#
# Hardware.fr est l'un des plus grands forums tech francophones.
# Sa section "Emploi" contient des offres de missions
# informatiques, développement web, SEO, etc.
#
# URL : https://forum.hardware.fr/hfr/Emploi/
#
# Structure forum myBB/vBulletin → HTML standard.
# =============================================================

import asyncio
import requests
from bs4 import BeautifulSoup
from config.settings import settings
from sources.utils import async_fetch

BASE_URL   = "https://forum.hardware.fr"
# Sections emploi / services
FORUM_URLS = [
    f"{BASE_URL}/hfr/Emploi/Offres-emploi/",
    f"{BASE_URL}/hfr/Emploi/Demandes-emploi/",
    f"{BASE_URL}/hfr/Emploi/",
]
HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Referer":         BASE_URL,
}

_OFFER_KEYWORDS = [
    "cherche", "recherche", "mission", "freelance", "prestataire",
    "développeur", "webmaster", "wordpress", "shopify", "création",
    "refonte", "web", "seo", "budget", "offre", "besoin",
]

_EXCLUDE_KEYWORDS = [
    "aide", "problème", "erreur", "tutoriel", "driver",
    "conseil", "avis", "question", "comment",
]


def _is_offer(title: str) -> bool:
    low = title.lower()
    has_offer    = any(kw in low for kw in _OFFER_KEYWORDS)
    has_excluded = sum(1 for kw in _EXCLUDE_KEYWORDS if kw in low) >= 2
    return has_offer and not has_excluded


def _abs(href: str) -> str:
    if not href:
        return ""
    if href.startswith("http"):
        return href
    return BASE_URL + "/" + href.lstrip("/")


async def get_hardware_fr_jobs() -> list:
    print("🕷️  [Hardware.fr] Scraping forum en cours...")
    jobs: list = []
    seen_urls: set = set()

    for forum_url in FORUM_URLS:
        try:
            resp = await async_fetch(forum_url, headers=HEADERS, timeout=20)
            if resp.status_code in (404, 403):
                continue
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Les topics forum sont généralement dans des <a> de type titre
            # Hardware.fr utilise des structures de type "topictitle" ou similaires
            topics = (
                soup.select("a.topictitle") or
                soup.select(".threadtitle a") or
                soup.select("a[href*='topic'], a[href*='thread']") or
                soup.select("td.tLeft a, td.alt1 a")
            )

            # Fallback : tous les liens internes significatifs
            if not topics:
                topics = [
                    a for a in soup.find_all("a", href=True)
                    if any(p in a.get("href", "") for p in ["topic", "thread", "post", "sujet"])
                ]

            for a in topics[:30]:
                title = a.get_text(strip=True)
                href  = a.get("href", "")
                link  = _abs(href)

                if not title or len(title) < 8 or not link or link in seen_urls:
                    continue

                if not _is_offer(title):
                    continue

                seen_urls.add(link)
                jobs.append({
                    "title":       title,
                    "description": "",
                    "url":         link,
                    "budget_raw":  "",
                    "source":      "hardware.fr",
                })

            await asyncio.sleep(settings.REQUEST_DELAY)

        except requests.RequestException as exc:
            print(f"  ❌ [Hardware.fr] {forum_url}: {exc}")
        except Exception as exc:
            print(f"  ⚠️  [Hardware.fr] parsing: {exc}")

    print(f"  ✅ [Hardware.fr] {len(jobs)} missions trouvées")
    return jobs
