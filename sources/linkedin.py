# =============================================================
# sources/linkedin.py — LinkedIn via JobSpy + fallback HTML
# =============================================================
#
# LinkedIn est la plus grande base d'offres du monde mais aussi
# la plus restrictive (rate-limit agressif, anti-bot).
#
# Stratégie en cascade :
#  1. JobSpy (lib Python) — wrapper robuste qui gère les proxies
#     et la rotation d'user-agent automatiquement
#     pip install python-jobspy
#  2. Fallback : scraping HTML direct du jobboard public LinkedIn
#     (sans auth, limité mais fonctionnel pour les résultats publics)
#
# Rate-limit connu : ~10 pages avant 429.
# On limite à 15 résultats par requête avec délai généreux.
# =============================================================

import asyncio
import re
import requests
from bs4 import BeautifulSoup
from config.settings import settings

BASE_URL   = "https://www.linkedin.com"
SEARCH_URL = (
    "https://www.linkedin.com/jobs/search/"
    "?keywords=développeur+freelance&location=France"
    "&f_WT=2&f_JT=C&sortBy=DD"           # remote + contract + recent
)
HEADERS    = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Accept":          "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
}

# Requêtes JobSpy
_JOBSPY_QUERIES = [
    {"search_term": "développeur web freelance",  "location": "France"},
    {"search_term": "react developer freelance",  "location": "France"},
    {"search_term": "wordpress developer remote", "location": "France"},
]


def _scrape_with_jobspy(query: str, location: str, n: int = 10) -> list:
    """Utilise JobSpy pour scraper LinkedIn."""
    try:
        from jobspy import scrape_jobs
        df = scrape_jobs(
            site_name=["linkedin"],
            search_term=query,
            location=location,
            results_wanted=n,
            hours_old=72,
            is_remote=True,
            country_indeed="France",
        )
        jobs = []
        for _, row in df.iterrows():
            title   = str(row.get("title", "") or "").strip()
            company = str(row.get("company", "") or "").strip()
            url     = str(row.get("job_url", "") or "").strip()
            desc    = str(row.get("description", "") or "").strip()[:500]
            salary  = str(row.get("min_amount", "") or "").strip()

            if not title or not url:
                continue
            full_title = f"{title} @ {company}".strip(" @") if company else title
            jobs.append({
                "title":       full_title,
                "description": desc,
                "url":         url,
                "budget_raw":  f"{salary} €" if salary and salary != "nan" else "",
                "source":      "linkedin",
            })
        return jobs

    except ImportError:
        raise ImportError("jobspy")
    except Exception as exc:
        print(f"  ⚠️  [LinkedIn/JobSpy] query='{query}': {exc}")
        return []


def _scrape_with_requests() -> list:
    """Fallback : scraping HTML public LinkedIn (sans auth)."""
    jobs = []
    try:
        resp = requests.get(SEARCH_URL, headers=HEADERS, timeout=20)
        # LinkedIn redirige souvent vers login — on détecte ça
        if "authwall" in resp.url or resp.status_code in (401, 403):
            print("  ⚠️  [LinkedIn/HTML] Redirigé vers authwall")
            return []
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Sélecteurs pour le jobboard public LinkedIn
        cards = (
            soup.select("li.jobs-search__results-list") or
            soup.select(".job-search-card") or
            soup.select("[class*='job-search-card']") or
            soup.select("li[class*='result']")
        )

        for card in cards[:15]:
            try:
                title_el = (
                    card.select_one("h3.base-search-card__title") or
                    card.select_one("h3") or
                    card.select_one("h2")
                )
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)

                company_el = (
                    card.select_one("h4.base-search-card__subtitle") or
                    card.select_one("h4")
                )
                company = company_el.get_text(strip=True) if company_el else ""

                link_el = card.select_one("a.base-card__full-link") or card.select_one("a")
                href    = link_el.get("href", "") if link_el else ""
                url     = href if href.startswith("http") else BASE_URL + href

                if title and url:
                    full_title = f"{title} @ {company}".strip(" @") if company else title
                    jobs.append({
                        "title":       full_title,
                        "description": "",
                        "url":         url,
                        "budget_raw":  "",
                        "source":      "linkedin",
                    })
            except Exception:
                continue

    except requests.RequestException as exc:
        print(f"  ❌ [LinkedIn/HTML] réseau: {exc}")

    return jobs


async def get_linkedin_jobs() -> list:
    print("🕷️  [LinkedIn] Scraping en cours...")

    all_jobs:  list = []
    seen_urls: set  = set()

    # ── Tentative JobSpy ─────────────────────────────────────
    jobspy_ok = False
    try:
        for q in _JOBSPY_QUERIES:
            batch = await asyncio.to_thread(
                _scrape_with_jobspy, q["search_term"], q["location"]
            )
            for job in batch:
                if job["url"] not in seen_urls:
                    seen_urls.add(job["url"])
                    all_jobs.append(job)
            await asyncio.sleep(settings.REQUEST_DELAY)
            if batch:
                jobspy_ok = True

    except ImportError:
        print("  ℹ️  [LinkedIn] JobSpy non installé → fallback HTML")
    except Exception as exc:
        print(f"  ⚠️  [LinkedIn] JobSpy erreur: {exc}")

    # ── Fallback HTML si JobSpy vide ou absent ───────────────
    if not jobspy_ok or not all_jobs:
        try:
            batch = await asyncio.to_thread(_scrape_with_requests)
            for job in batch:
                if job["url"] not in seen_urls:
                    seen_urls.add(job["url"])
                    all_jobs.append(job)
            await asyncio.sleep(settings.REQUEST_DELAY)
        except Exception as exc:
            print(f"  ❌ [LinkedIn] fallback HTML échoué: {exc}")

    print(f"  ✅ [LinkedIn] {len(all_jobs)} missions trouvées")
    return all_jobs
