# =============================================================
# sources/facebook_groups.py — Groupes Facebook (Playwright)
# =============================================================
#
# Facebook nécessite une authentification pour accéder aux groupes.
# Ce scraper utilise Playwright avec une session persistante
# (cookies sauvegardés après le premier login manuel).
#
# ⚙️  CONFIGURATION REQUISE dans .env :
#
#   FB_COOKIES_PATH=/app/data/fb_cookies.json
#   FB_ENABLED=true
#
# 📋 PROCÉDURE D'INITIALISATION (une seule fois) :
#
#   1. Lancer : python -m sources.facebook_groups --login
#   2. Un navigateur Chromium s'ouvre → te connecter manuellement
#   3. Les cookies sont sauvegardés dans FB_COOKIES_PATH
#   4. Le scraper réutilise la session lors des cycles suivants
#
# 🎯 Groupes ciblés (configurable dans FB_GROUPS) :
#   - "Freelance France"
#   - "WordPress France"
#   - "Entrepreneurs France"
#   - "Shopify France"
#   - "Développeurs Web France"
#
# ⚠️  RISQUES :
#   - Facebook détecte l'automatisation → possibilité de ban
#   - Les cookies expirent (~90 jours) → reconnexion manuelle
#   - Les URLs de groupes changent → mettre à jour FB_GROUPS
#
# =============================================================

import asyncio
import json
import os
import re
import sys
from datetime import datetime
from config.settings import settings
from sources.utils import async_fetch  # noqa: F401 (pour cohérence)

# ── Configuration ─────────────────────────────────────────────

FB_COOKIES_PATH: str = os.getenv("FB_COOKIES_PATH", "data/fb_cookies.json")
FB_ENABLED:      bool = os.getenv("FB_ENABLED", "false").lower() == "true"

# Groupes à scraper (URL complète ou identifiant numérique)
FB_GROUPS: list = [
    "https://www.facebook.com/groups/freelancefrance/",
    "https://www.facebook.com/groups/wordpressfrance/",
    "https://www.facebook.com/groups/entrepreneursfrance/",
    "https://www.facebook.com/groups/shopifyfrance/",
    "https://www.facebook.com/groups/developpeursweb/",
]

# Mots-clés dans les posts qui signalent une demande de mission
_OFFER_KEYWORDS = [
    "cherche", "recherche", "besoin", "mission", "freelance",
    "prestataire", "développeur", "webmaster", "wordpress",
    "shopify", "création", "refonte", "site web", "seo",
    "budget", "rémunéré", "payé", "projet", "devis",
    "qui peut", "quelqu'un pour", "besoin d'aide",
]

_EXCLUDE_KEYWORDS = [
    "vends", "vente", "achète", "cherche emploi", "je cherche un emploi",
    "recrutement", "je suis disponible", "je propose",  # offres de service, pas demandes
]


def _is_offer(text: str) -> bool:
    low = text.lower()
    has_offer    = any(kw in low for kw in _OFFER_KEYWORDS)
    has_excluded = any(kw in low for kw in _EXCLUDE_KEYWORDS)
    return has_offer and not has_excluded


def _load_cookies() -> list | None:
    """Charge les cookies Facebook depuis le fichier JSON."""
    if not os.path.exists(FB_COOKIES_PATH):
        print(f"  ⚠️  [Facebook] Cookies non trouvés : {FB_COOKIES_PATH}")
        print("     → Lance : python -m sources.facebook_groups --login")
        return None
    try:
        with open(FB_COOKIES_PATH, "r") as f:
            return json.load(f)
    except Exception as exc:
        print(f"  ❌ [Facebook] Erreur lecture cookies : {exc}")
        return None


def _save_cookies(cookies: list):
    """Sauvegarde les cookies après login."""
    os.makedirs(os.path.dirname(FB_COOKIES_PATH) or ".", exist_ok=True)
    with open(FB_COOKIES_PATH, "w") as f:
        json.dump(cookies, f, indent=2)
    print(f"  ✅ [Facebook] Cookies sauvegardés : {FB_COOKIES_PATH}")


async def _scrape_group(page, group_url: str) -> list:
    """Scrape les posts récents d'un groupe Facebook."""
    jobs = []
    try:
        await page.goto(group_url, wait_until="domcontentloaded", timeout=30_000)
        await asyncio.sleep(3)  # Attendre le JS

        # Scroll pour charger plus de posts
        for _ in range(3):
            await page.keyboard.press("End")
            await asyncio.sleep(2)

        # Extraire le texte des posts récents
        # Facebook utilise des data-attributes qui changent souvent
        post_selectors = [
            "[data-testid='post_message']",
            "[class*='userContent']",
            "div[role='article'] div[dir='auto']",
            "div[data-ad-preview='message']",
        ]

        posts_text = []
        for sel in post_selectors:
            elements = await page.query_selector_all(sel)
            if elements:
                for el in elements[:20]:
                    try:
                        text = (await el.inner_text()).strip()
                        if text and len(text) > 20:
                            posts_text.append(text)
                    except Exception:
                        continue
                if posts_text:
                    break

        # Extraire aussi les liens des posts
        post_links = await page.evaluate("""
            () => {
                const links = [];
                document.querySelectorAll('a[href*="/groups/"][href*="/posts/"]').forEach(a => {
                    if (a.href && !links.includes(a.href)) links.push(a.href);
                });
                return links.slice(0, 20);
            }
        """)

        group_name = re.search(r"/groups/([^/]+)/", group_url)
        group_label = group_name.group(1) if group_name else "fb-group"

        for i, text in enumerate(posts_text):
            if not _is_offer(text):
                continue
            # Titre = 1ère ligne ou premiers 80 chars
            title = text.split("\n")[0].strip()[:80] or text[:80]
            url   = post_links[i] if i < len(post_links) else group_url

            jobs.append({
                "title":       title,
                "description": text[:500],
                "url":         url,
                "budget_raw":  "",
                "source":      f"facebook/{group_label}",
            })

    except Exception as exc:
        print(f"  ⚠️  [Facebook] {group_url}: {exc}")

    return jobs


async def get_facebook_groups_jobs() -> list:
    """
    Scrape les groupes Facebook configurés via Playwright.
    Nécessite : FB_ENABLED=true et cookies valides dans FB_COOKIES_PATH.
    """
    if not FB_ENABLED:
        return []  # Désactivé par défaut

    print("🕷️  [Facebook Groups] Scraping en cours (Playwright)...")

    cookies = _load_cookies()
    if cookies is None:
        return []

    jobs: list = []
    seen_urls: set = set()

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                ],
            )

            # Contexte avec session persistante
            ctx = await browser.new_context(
                locale="fr-FR",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
            )

            # Injecter les cookies de session
            await ctx.add_cookies(cookies)

            page = await ctx.new_page()

            # Vérifier que la session est toujours valide
            await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=20_000)
            await asyncio.sleep(2)

            if "login" in page.url.lower() or "checkpoint" in page.url.lower():
                print("  ⚠️  [Facebook] Session expirée → relancer --login")
                await browser.close()
                return []

            print(f"  ✅ [Facebook] Session valide — scraping {len(FB_GROUPS)} groupes")

            for group_url in FB_GROUPS:
                batch = await _scrape_group(page, group_url)
                for job in batch:
                    if job["url"] not in seen_urls:
                        seen_urls.add(job["url"])
                        jobs.append(job)
                await asyncio.sleep(settings.REQUEST_DELAY + 2)  # Délai généreux anti-ban

            # Mettre à jour les cookies (peuvent avoir changé)
            updated_cookies = await ctx.cookies()
            if updated_cookies:
                _save_cookies(updated_cookies)

            await browser.close()

    except ImportError:
        print("  ⚠️  [Facebook] Playwright non installé → pip install playwright")
    except Exception as exc:
        print(f"  ❌ [Facebook] Erreur: {exc}")

    print(f"  ✅ [Facebook] {len(jobs)} missions trouvées")
    return jobs


# ── Mode login manuel (python -m sources.facebook_groups --login) ──

async def _interactive_login():
    """
    Ouvre un navigateur visible pour se connecter manuellement à Facebook.
    Les cookies sont sauvegardés après connexion pour les sessions suivantes.
    """
    print("🔐 [Facebook] Mode login interactif")
    print("   Un navigateur va s'ouvrir. Connecte-toi à Facebook manuellement.")
    print("   Une fois connecté, appuie sur ENTRÉE ici pour sauvegarder la session.")

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=False,  # Mode visible pour login manuel
                args=["--no-sandbox"],
            )
            ctx  = await browser.new_context(locale="fr-FR")
            page = await ctx.new_page()

            await page.goto("https://www.facebook.com/login", wait_until="domcontentloaded")
            print("   Navigue vers Facebook et connecte-toi...")

            input("\n   ✅ Connecté ? Appuie sur ENTRÉE pour sauvegarder les cookies...")

            cookies = await ctx.cookies()
            _save_cookies(cookies)
            print(f"\n   ✅ {len(cookies)} cookies sauvegardés dans {FB_COOKIES_PATH}")
            print("   Tu peux maintenant activer FB_ENABLED=true dans .env")

            await browser.close()

    except ImportError:
        print("❌ Playwright non installé : pip install playwright && playwright install chromium")


if __name__ == "__main__":
    if "--login" in sys.argv:
        asyncio.run(_interactive_login())
    else:
        print("Usage : python -m sources.facebook_groups --login")
