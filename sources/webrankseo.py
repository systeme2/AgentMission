# =============================================================
# sources/webrankseo.py — Forum WebRankInfo (WebRankSEO)
# =============================================================
#
# WebRankInfo (webrankseo.com) est LA référence des forums SEO/web
# francophones. La section "Annonces" et "Freelances & Agences"
# regorge de demandes de missions web, SEO, développement.
#
# Structure : forum phpBB → HTML standard, scraping facile.
#
# Sections utiles :
#   - Offres freelance & emploi
#   - Annonces générales web
# =============================================================

import asyncio
import re
import requests
from bs4 import BeautifulSoup
from config.settings import settings
from sources.utils import async_fetch

BASE_URL = "https://www.webrankseo.com"
FORUM_BASE = f"{BASE_URL}/forum"

# Sections du forum à scraper (IDs phpBB courants — adapter si besoin)
FORUM_URLS = [
    f"{FORUM_BASE}/viewforum.php?f=48",   # Offres d'emploi / freelance
    f"{FORUM_BASE}/viewforum.php?f=12",   # Annonces webmaster
    f"{FORUM_BASE}/viewforum.php?f=6",    # Référencement / SEO missions
]

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Referer":         BASE_URL,
}

# Mots-clés qui signalent une offre de mission (pas une demande de conseil)
_OFFER_KEYWORDS = [
    "cherche", "recherche", "besoin", "mission", "freelance",
    "prestataire", "développeur", "webmaster", "création", "refonte",
    "wordpress", "shopify", "seo", "référencement", "budget",
]

# Mots à exclure (questions techniques, pas des offres)
_EXCLUDE_KEYWORDS = [
    "comment faire", "tutoriel", "aide", "erreur", "problème",
    "question", "conseil", "avis", "plugin", "theme", "template",
]


def _is_offer(title: str, desc: str = "") -> bool:
    text = (title + " " + desc).lower()
    has_offer    = any(kw in text for kw in _OFFER_KEYWORDS)
    has_excluded = sum(1 for kw in _EXCLUDE_KEYWORDS if kw in text) >= 2
    return has_offer and not has_excluded


def _abs(href: str) -> str:
    if not href:
        return ""
    if href.startswith("http"):
        return href
    return FORUM_BASE + "/" + href.lstrip("./")


async def get_webrankseo_jobs() -> list:
    print("🕷️  [WebRankSEO] Scraping forum en cours...")
    jobs: list = []
    seen_urls: set = set()

    for forum_url in FORUM_URLS:
        try:
            resp = await async_fetch(forum_url, headers=HEADERS, timeout=20)
            if resp.status_code in (404, 403):
                continue
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # phpBB : les topics sont dans des <a> avec href viewtopic.php
            topics = soup.select("a[href*='viewtopic']")

            # Fallback : n'importe quel <a> qui pointe vers un topic
            if not topics:
                topics = soup.select("a[href*='topic'], a[href*='thread'], a[href*='post']")

            for a in topics[:30]:
                title = a.get_text(strip=True)
                href  = a.get("href", "")
                link  = _abs(href)

                if not title or len(title) < 10 or not link or link in seen_urls:
                    continue

                if not _is_offer(title):
                    continue

                seen_urls.add(link)
                jobs.append({
                    "title":       title,
                    "description": "",
                    "url":         link,
                    "budget_raw":  "",
                    "source":      "webrankseo",
                })

            await asyncio.sleep(settings.REQUEST_DELAY)

        except requests.RequestException as exc:
            print(f"  ❌ [WebRankSEO] {forum_url}: {exc}")
        except Exception as exc:
            print(f"  ⚠️  [WebRankSEO] parsing: {exc}")

    print(f"  ✅ [WebRankSEO] {len(jobs)} missions trouvées")
    return jobs
