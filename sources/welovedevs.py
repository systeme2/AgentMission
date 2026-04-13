# =============================================================
# sources/welovedevs.py — scraper WeLoveDevs (API publique)
# =============================================================

import asyncio
import requests
from config.settings import settings

HEADERS = {"User-Agent": "Mozilla/5.0"}


async def get_welovedevs_jobs() -> list:
    print("🕷️  [WeLoveDevs] Scraping en cours...")
    jobs = []

    try:
        # WeLoveDevs a une API publique partielle
        url = "https://welovedevs.com/app/api/joboffers?page=0&size=20&remote=true"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        offers = data.get("content", data if isinstance(data, list) else [])

        for offer in offers[:20]:
            title = offer.get("title") or offer.get("name", "")
            company = offer.get("company", {})
            company_name = company.get("name", "") if isinstance(company, dict) else ""
            slug = offer.get("slug") or offer.get("id", "")
            link = f"https://welovedevs.com/app/jobs/{slug}"
            description = offer.get("description", "")[:500]

            if title:
                jobs.append({
                    "title": f"{title} @ {company_name}".strip(" @"),
                    "description": description,
                    "url": link,
                    "source": "welovedevs",
                    "budget_raw": "",
                })

        await asyncio.sleep(settings.REQUEST_DELAY)

    except Exception as e:
        print(f"  ⚠️  [WeLoveDevs] Erreur: {e}")

    print(f"  ✅ [WeLoveDevs] {len(jobs)} missions trouvées")
    return jobs


# =============================================================
# sources/remixjobs.py — scraper RemixJobs RSS
# =============================================================

import xml.etree.ElementTree as ET


async def get_remixjobs_jobs() -> list:
    """RemixJobs expose un flux RSS public."""
    print("🕷️  [RemixJobs] Scraping RSS en cours...")
    jobs = []

    try:
        url = "https://remixjobs.com/emploi/Freelance/page/1.rss"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()

        root = ET.fromstring(resp.content)
        items = root.findall(".//item")

        for item in items[:20]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            description = (item.findtext("description") or "").strip()[:500]

            # Nettoyer le HTML dans la description
            try:
                from bs4 import BeautifulSoup
                description = BeautifulSoup(description, "html.parser").get_text()[:500]
            except Exception:
                pass

            if title and link:
                jobs.append({
                    "title": title,
                    "description": description,
                    "url": link,
                    "source": "remixjobs",
                    "budget_raw": "",
                })

        await asyncio.sleep(settings.REQUEST_DELAY)

    except Exception as e:
        print(f"  ⚠️  [RemixJobs] Erreur: {e}")

    print(f"  ✅ [RemixJobs] {len(jobs)} missions trouvées")
    return jobs
