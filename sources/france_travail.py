# =============================================================
# sources/france_travail.py — France Travail (ex-Pôle Emploi)
# =============================================================
#
# France Travail expose une API REST officielle et gratuite.
# Elle contient des CDD courts souvent transformables en mission
# freelance, et des offres explicitement en "prestataire".
#
# ⚙️  CONFIGURATION (.env) :
#
#   FT_CLIENT_ID=xxx          # Depuis francetravail.io/connexion
#   FT_CLIENT_SECRET=xxx      # Inscription gratuite sur le portail
#
# Sans clés → fallback RSS public (limité mais fonctionnel)
#
# 📋 INSCRIPTION API (gratuite) :
#   1. https://francetravail.io/data/api/offres-emploi
#   2. "S'inscrire" → créer une application → récupérer les clés
#   3. Ajouter FT_CLIENT_ID et FT_CLIENT_SECRET dans .env
#
# API Doc : https://api.francetravail.io/partenaire/offresdemploi
# =============================================================

import asyncio
import os
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
from config.settings import settings
from sources.utils import async_fetch

# ── Configuration ─────────────────────────────────────────────
FT_CLIENT_ID:     str = os.getenv("FT_CLIENT_ID", "")
FT_CLIENT_SECRET: str = os.getenv("FT_CLIENT_SECRET", "")

BASE_API   = "https://api.francetravail.io/partenaire/offresdemploi/v2"
TOKEN_URL  = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire"

# Fallback RSS public (sans auth)
RSS_URLS = [
    "https://candidat.francetravail.fr/offres/recherche/rss?motsCles=freelance+wordpress&typeContrat=CDD&sort=1",
    "https://candidat.francetravail.fr/offres/recherche/rss?motsCles=freelance+shopify&typeContrat=CDD&sort=1",
    "https://candidat.francetravail.fr/offres/recherche/rss?motsCles=création+site+web+freelance&sort=1",
    "https://candidat.francetravail.fr/offres/recherche/rss?motsCles=prestataire+développeur+web&sort=1",
    "https://candidat.francetravail.fr/offres/recherche/rss?motsCles=SEO+freelance&sort=1",
]

HEADERS = {
    "User-Agent": "MissionAgentBot/1.0 (personal freelance tracker)",
    "Accept":     "application/json, application/rss+xml, application/xml, */*",
}

# Mots-clés dans le titre/desc qui signalent une vraie mission freelance
_OFFER_KEYWORDS = [
    "freelance", "prestataire", "indépendant", "auto-entrepreneur",
    "mission", "création site", "refonte", "wordpress", "shopify",
    "seo", "référencement", "développeur web", "webmaster",
]


def _is_relevant(title: str, desc: str = "") -> bool:
    text = (title + " " + desc).lower()
    return any(kw in text for kw in _OFFER_KEYWORDS)


def _clean_html(text: str) -> str:
    try:
        return BeautifulSoup(text or "", "html.parser").get_text()[:500]
    except Exception:
        return (text or "")[:500]


# ── Méthode 1 : API officielle avec OAuth2 ────────────────────

def _get_access_token() -> str | None:
    """Obtient un token OAuth2 pour l'API France Travail."""
    if not FT_CLIENT_ID or not FT_CLIENT_SECRET:
        return None
    try:
        resp = requests.post(
            TOKEN_URL,
            data={
                "grant_type":    "client_credentials",
                "client_id":     FT_CLIENT_ID,
                "client_secret": FT_CLIENT_SECRET,
                "scope":         "api_offresdemploiv2 o2dsoffre",
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("access_token")
    except Exception as exc:
        print(f"  ⚠️  [FranceTravail] Token OAuth2: {exc}")
        return None


async def _scrape_with_api(token: str) -> list:
    """Scrape via l'API officielle France Travail."""
    jobs: list = []
    seen_ids: set = set()

    # Requêtes ciblées pour profil web/WP/Shopify/SEO
    searches = [
        {"motsCles": "wordpress freelance",       "typeContrat": "CDD,MIS"},
        {"motsCles": "shopify freelance",          "typeContrat": "CDD,MIS"},
        {"motsCles": "création site web freelance","typeContrat": "CDD,MIS"},
        {"motsCles": "prestataire développeur web","typeContrat": "CDD,MIS"},
        {"motsCles": "référencement SEO freelance","typeContrat": "CDD,MIS"},
    ]

    auth_headers = {**HEADERS, "Authorization": f"Bearer {token}"}

    for search in searches[:3]:  # 3 requêtes max
        try:
            params = {
                **search,
                "range":     "0-14",
                "sort":      "1",   # tri par date
                "publieeDepuis": "3",  # publiée depuis 3 jours max
            }
            resp = await async_fetch(
                f"{BASE_API}/offres/search",
                headers=auth_headers,
                params=params,
                timeout=15,
            )

            if resp.status_code == 206:  # Partial Content = résultats OK
                data   = resp.json()
                offers = data.get("resultats", [])
            elif resp.status_code == 200:
                data   = resp.json()
                offers = data.get("resultats", data if isinstance(data, list) else [])
            else:
                continue

            for offer in offers:
                offer_id = offer.get("id", "")
                if offer_id in seen_ids:
                    continue

                title   = (offer.get("intitule") or "").strip()
                desc    = (offer.get("description") or "")[:500]
                url     = offer.get("origineOffre", {}).get("urlOrigine") or \
                          f"https://candidat.francetravail.fr/offres/recherche/detail/{offer_id}"
                budget  = str(offer.get("salaire", {}).get("libelle") or "")
                company = (offer.get("entreprise", {}) or {}).get("nom", "")

                if not title or not _is_relevant(title, desc):
                    continue

                seen_ids.add(offer_id)
                full_title = f"{title} @ {company}".strip(" @") if company else title
                jobs.append({
                    "title":       full_title,
                    "description": desc,
                    "url":         url,
                    "budget_raw":  budget,
                    "source":      "france-travail",
                })

            await asyncio.sleep(0.5)  # Respecter le rate-limit API

        except Exception as exc:
            print(f"  ⚠️  [FranceTravail] API search: {exc}")

    return jobs


# ── Méthode 2 : Fallback RSS public (sans auth) ───────────────

async def _scrape_with_rss() -> list:
    """Fallback : RSS public France Travail (sans authentification)."""
    jobs: list = []
    seen_urls: set = set()

    for rss_url in RSS_URLS[:3]:
        try:
            resp = await async_fetch(rss_url, headers=HEADERS, timeout=20)
            if resp.status_code in (404, 403):
                continue
            resp.raise_for_status()

            root  = ET.fromstring(resp.content)
            items = root.findall(".//item")

            for item in items[:15]:
                title = (item.findtext("title") or "").strip()
                link  = (item.findtext("link")  or "").strip()
                desc  = _clean_html(item.findtext("description") or "")

                if not title or not link or link in seen_urls:
                    continue
                if not _is_relevant(title, desc):
                    continue

                seen_urls.add(link)
                jobs.append({
                    "title":       title,
                    "description": desc,
                    "url":         link,
                    "budget_raw":  "",
                    "source":      "france-travail",
                })

            await asyncio.sleep(settings.REQUEST_DELAY)

        except ET.ParseError as exc:
            print(f"  ⚠️  [FranceTravail] RSS XML invalide: {exc}")
        except Exception as exc:
            print(f"  ❌ [FranceTravail] RSS {exc}")

    return jobs


# ── Point d'entrée ────────────────────────────────────────────

async def get_france_travail_jobs() -> list:
    print("🕷️  [France Travail] Scraping en cours...")

    # Tentative API officielle (si clés configurées)
    token = await asyncio.to_thread(_get_access_token)
    if token:
        print("  🔑 [France Travail] API officielle (OAuth2)")
        jobs = await _scrape_with_api(token)
        if jobs:
            print(f"  ✅ [France Travail] {len(jobs)} missions (API)")
            return jobs

    # Fallback RSS public
    print("  ℹ️  [France Travail] Fallback RSS public")
    jobs = await _scrape_with_rss()
    print(f"  ✅ [France Travail] {len(jobs)} missions (RSS)")
    return jobs
