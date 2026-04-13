# =============================================================
# sources/rss_custom.py — Flux RSS personnalisés
# =============================================================
#
# Scrape n'importe quel flux RSS/Atom configuré dans
# settings.CUSTOM_RSS_FEEDS.
#
# Cas d'usage :
#   - Blog d'une agence qui publie ses besoins en freelance
#   - Newsletter convertie en RSS
#   - Jobboard niche non couvert par les autres sources
#   - Flux RSS d'une communauté Slack ou Discord
#   - Site client avec flux RSS de leurs offres
#
# Ajoute des URLs dans settings.CUSTOM_RSS_FEEDS pour activer.
#
# Support RSS 2.0, RSS 1.0 (RDF), Atom 1.0
# =============================================================

import asyncio
import re
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
from config.settings import settings

HEADERS = {
    "User-Agent": "MissionAgentBot/1.0 (personal freelance tracker)",
    "Accept":     "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
}

# Namespaces courants RSS/Atom
_NS = {
    "atom":    "http://www.w3.org/2005/Atom",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc":      "http://purl.org/dc/elements/1.1/",
    "media":   "http://search.yahoo.com/mrss/",
}


def _clean_html(text: str, max_len: int = 500) -> str:
    """Nettoie le HTML d'une description RSS."""
    try:
        text = BeautifulSoup(text or "", "html.parser").get_text()
    except Exception:
        text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def _parse_rss2(root: ET.Element, feed_url: str) -> list:
    """Parse un flux RSS 2.0."""
    jobs  = []
    items = root.findall(".//item")
    for item in items[:25]:
        title = (item.findtext("title") or "").strip()
        link  = (item.findtext("link")  or "").strip()
        desc  = (item.findtext("description") or
                 item.findtext(f"{{{_NS['content']}}}encoded") or "")
        pub   = (item.findtext("pubDate") or "").strip()

        if not title or not link:
            continue
        jobs.append({
            "title":       title,
            "description": _clean_html(desc),
            "url":         link,
            "budget_raw":  "",
            "source":      f"rss:{_domain(feed_url)}",
            "date":        pub,
        })
    return jobs


def _parse_atom(root: ET.Element, feed_url: str) -> list:
    """Parse un flux Atom 1.0."""
    atom  = _NS["atom"]
    jobs  = []
    for entry in root.findall(f"{{{atom}}}entry")[:25]:
        title   = (entry.findtext(f"{{{atom}}}title") or "").strip()
        _link_alt = entry.find(f"{{{atom}}}link[@rel='alternate']")
        link_el   = _link_alt if _link_alt is not None else entry.find(f"{{{atom}}}link")
        link    = (link_el.get("href", "") if link_el is not None else "").strip()
        summary = (entry.findtext(f"{{{atom}}}summary") or
                   entry.findtext(f"{{{atom}}}content") or "")
        pub     = (entry.findtext(f"{{{atom}}}published") or
                   entry.findtext(f"{{{atom}}}updated") or "")

        if not title or not link:
            continue
        jobs.append({
            "title":       title,
            "description": _clean_html(summary),
            "url":         link,
            "budget_raw":  "",
            "source":      f"rss:{_domain(feed_url)}",
            "date":        pub,
        })
    return jobs


def _domain(url: str) -> str:
    """Extrait le domaine d'une URL pour le label source."""
    m = re.search(r"https?://([^/]+)", url)
    return m.group(1).replace("www.", "") if m else url[:30]


def _fetch_feed(url: str) -> list:
    """Télécharge et parse un flux RSS/Atom."""
    jobs = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()

        root = ET.fromstring(resp.content)
        tag  = root.tag.lower()

        # Atom
        if "atom" in tag or "feed" in tag:
            jobs = _parse_atom(root, url)
        # RSS 2.0
        elif "rss" in tag or "channel" in root.tag.lower():
            jobs = _parse_rss2(root, url)
        else:
            # Tentative RSS dans un sous-élément
            channel = root.find("channel")
            if channel is not None:
                jobs = _parse_rss2(root, url)
            else:
                jobs = _parse_atom(root, url)

    except ET.ParseError as exc:
        print(f"  ⚠️  [RSS Custom] XML invalide {_domain(url)}: {exc}")
    except requests.RequestException as exc:
        print(f"  ❌ [RSS Custom] réseau {_domain(url)}: {exc}")

    return jobs


async def get_custom_rss_jobs() -> list:
    feeds = getattr(settings, "CUSTOM_RSS_FEEDS", [])
    if not feeds:
        return []

    print(f"🕷️  [RSS Custom] {len(feeds)} flux configuré(s)...")

    all_jobs:  list = []
    seen_urls: set  = set()

    for feed_url in feeds:
        batch = await asyncio.to_thread(_fetch_feed, feed_url)
        for job in batch:
            if job["url"] not in seen_urls:
                seen_urls.add(job["url"])
                all_jobs.append(job)
        await asyncio.sleep(settings.REQUEST_DELAY)

    print(f"  ✅ [RSS Custom] {len(all_jobs)} missions trouvées")
    return all_jobs
