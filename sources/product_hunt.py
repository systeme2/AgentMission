# =============================================================
# sources/product_hunt.py — Product Hunt (startups FR)
# =============================================================
#
# Product Hunt liste les nouveaux produits lancés chaque jour.
# Les startups françaises qui se lancent ont souvent besoin
# de développeurs freelance rapidement.
#
# Stratégies :
#   1. RSS public : https://www.producthunt.com/feed (top du jour)
#   2. API GraphQL publique pour filtrer les startups FR
#
# On détecte les startups FR via : pays, langue, description FR
# =============================================================

import asyncio
import re
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
from config.settings import settings
from sources.utils import async_fetch

BASE_URL = "https://www.producthunt.com"
RSS_URL  = f"{BASE_URL}/feed"

HEADERS = {
    "User-Agent": "MissionAgentBot/1.0 (personal freelance tracker)",
    "Accept":     "application/rss+xml, application/xml, text/xml, */*",
}

# Marqueurs FR dans les descriptions
_FR_MARKERS = [
    "french", "france", "français", "francophone", "fr startup",
    "paris", "lyon", "marseille", "bordeaux", "nantes",
    "made in france", "produit français",
]

# Mots-clés qui signalent un besoin de dev (dans la description)
_DEV_NEEDS = [
    "looking for developer", "need developer", "hiring developer",
    "cherche développeur", "recherche développeur", "besoin dev",
    "co-founder", "technical co-founder", "cofondateur tech",
    "cto", "full-stack", "frontend", "backend", "mobile",
]


def _clean(text: str) -> str:
    try:
        return BeautifulSoup(text or "", "html.parser").get_text()[:500]
    except Exception:
        return re.sub(r"<[^>]+>", " ", text or "")[:500]


def _is_relevant(title: str, desc: str) -> bool:
    """Garde les produits qui semblent FR ou avec besoin de dev."""
    text = (title + " " + desc).lower()
    # Startup FR OU besoin de dev explicite
    is_fr   = any(m in text for m in _FR_MARKERS)
    needs_dev = any(kw in text for kw in _DEV_NEEDS)
    return is_fr or needs_dev


async def get_product_hunt_jobs() -> list:
    print("🕷️  [ProductHunt] Scraping RSS en cours...")
    jobs: list = []
    seen_urls: set = set()

    try:
        resp = await async_fetch(RSS_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()

        root  = ET.fromstring(resp.content)
        items = root.findall(".//item")

        for item in items[:30]:
            title = (item.findtext("title") or "").strip()
            link  = (item.findtext("link")  or "").strip()
            desc  = _clean(item.findtext("description") or "")
            # Product Hunt RSS inclut aussi <content:encoded>
            content_ns = "{http://purl.org/rss/1.0/modules/content/}encoded"
            full_desc  = _clean(item.findtext(content_ns) or desc)

            if not title or not link or link in seen_urls:
                continue

            # On prend tout depuis PH mais on enrichit le titre avec "(PH Launch)"
            # pour que le scorer IA puisse filtrer selon profil
            seen_urls.add(link)
            jobs.append({
                "title":       f"{title} [PH Launch]",
                "description": full_desc or desc,
                "url":         link,
                "budget_raw":  "",
                "source":      "producthunt",
            })

        await asyncio.sleep(settings.REQUEST_DELAY)

    except ET.ParseError as exc:
        print(f"  ⚠️  [ProductHunt] XML invalide: {exc}")
    except Exception as exc:
        print(f"  ❌ [ProductHunt] {exc}")

    print(f"  ✅ [ProductHunt] {len(jobs)} lancements trouvés")
    return jobs
