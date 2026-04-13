# =============================================================
# sources/upwork.py — scraper Upwork via RSS public
# =============================================================
#
# Upwork expose des flux RSS publics par catégorie et mots-clés.
# Format : https://www.upwork.com/ab/feed/jobs/rss?q=...&sort=recency
#
# Avantages : pas de JS, pas de auth, données structurées XML.
# Limites : ~10 résultats par flux, rate-limit généreux.
#
# On requête plusieurs flux thématiques en parallèle puis on
# déduplique par URL avant de retourner.
# =============================================================

import asyncio
import re
import requests
import xml.etree.ElementTree as ET
from urllib.parse import urlencode
from config.settings import settings

BASE_URL = "https://www.upwork.com"
RSS_BASE = f"{BASE_URL}/ab/feed/jobs/rss"

HEADERS  = {
    "User-Agent":      "Mozilla/5.0 (compatible; MissionAgentBot/1.0)",
    "Accept":          "application/rss+xml, application/xml, text/xml",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

# Requêtes thématiques — on les filtre ensuite avec les mots-clés du scorer
_QUERIES = [
    {"q": "wordpress developer",       "category2_uid": "531770282580668418"},
    {"q": "react developer freelance", "category2_uid": "531770282580668418"},
    {"q": "web developer site",        "category2_uid": "531770282580668418"},
    {"q": "seo freelance",             "category2_uid": "531770282580668418"},
    {"q": "nextjs developer",          "category2_uid": "531770282580668418"},
]

_NS = {
    "upwork": "http://www.upwork.com",
    "media":  "http://search.yahoo.com/mrss/",
}


def _clean_html(text: str) -> str:
    """Enlève les balises HTML d'une description RSS."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:500]


def _parse_budget_from_desc(desc: str) -> str:
    """Extrait le budget depuis la description RSS Upwork."""
    # Upwork met souvent : "Budget: $500" ou "Hourly Rate: $25-$50"
    m = re.search(r"(Budget|Hourly Rate)\s*:\s*\$[\d,\.\-]+", desc, re.IGNORECASE)
    return m.group(0) if m else ""


def _fetch_rss(query_params: dict) -> list:
    """Télécharge et parse un flux RSS Upwork."""
    jobs = []
    params = {**query_params, "sort": "recency", "paging": "0;10"}
    url    = RSS_BASE + "?" + urlencode(params)

    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()

        root  = ET.fromstring(resp.content)
        items = root.findall(".//item")

        for item in items:
            title    = (item.findtext("title") or "").strip()
            link     = (item.findtext("link")  or "").strip()
            desc_raw = (item.findtext("description") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()

            if not title or not link:
                continue

            desc   = _clean_html(desc_raw)
            budget = _parse_budget_from_desc(desc_raw)

            # Upwork links: https://www.upwork.com/jobs/...
            if not link.startswith("http"):
                link = BASE_URL + link

            jobs.append({
                "title":       title,
                "description": desc,
                "url":         link,
                "budget_raw":  budget,
                "source":      "upwork",
                "date":        pub_date,
            })

    except ET.ParseError as exc:
        print(f"  ⚠️  [Upwork] XML invalide pour {query_params.get('q','?')}: {exc}")
    except requests.RequestException as exc:
        print(f"  ⚠️  [Upwork] réseau pour {query_params.get('q','?')}: {exc}")

    return jobs


async def get_upwork_jobs() -> list:
    print("🕷️  [Upwork] Scraping RSS en cours...")
    all_jobs: list  = []
    seen_urls: set  = set()

    for qp in _QUERIES:
        batch = await asyncio.to_thread(_fetch_rss, qp)
        for job in batch:
            if job["url"] not in seen_urls:
                seen_urls.add(job["url"])
                all_jobs.append(job)
        await asyncio.sleep(settings.REQUEST_DELAY)

    print(f"  ✅ [Upwork] {len(all_jobs)} missions trouvées")
    return all_jobs
