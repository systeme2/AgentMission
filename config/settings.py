# =============================================================
# SETTINGS — mission-agent v2
# =============================================================

import os
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class Settings:
    # --- Telegram ---
    TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN", "TON_BOT_TOKEN_ICI")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "TON_CHAT_ID_ICI")

    # --- OpenAI ---
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "sk-...")
    OPENAI_MODEL: str = "gpt-4o-mini"

    # --- Scraping ---
    REQUEST_DELAY: float = 2.0
    LOOP_INTERVAL: int = 300        # toutes les 5 minutes

    # --- Score minimum pour notifier ---
    MIN_SCORE: float = 0.4

    # --- Profil actif (voir config/profiles.py) ---
    # "all" = comportement historique (tous les keywords, toutes les sources)
    # "wordpress" | "react" | "seo" | "international" | ton profil custom
    ACTIVE_PROFILE: str = os.getenv("ACTIVE_PROFILE", "all")

    # --- Tes préférences (utilisées par le profil "all") ---
    PREFERRED_KEYWORDS: List[str] = field(default_factory=lambda: [
        # CMS & e-commerce
        "wordpress", "shopify", "woocommerce", "elementor", "divi",
        "wix", "squarespace", "prestashop",
        # Types de missions
        "création de site", "créer un site", "refonte", "refonte site",
        "site vitrine", "site web", "boutique en ligne", "e-commerce",
        "landing page", "site wordpress", "site shopify",
        # Métier
        "développeur web", "intégrateur", "webmaster", "freelance",
        # Contexte FR
        "mission freelance", "prestataire",
    ])
    NEGATIVE_KEYWORDS: List[str] = field(default_factory=lambda: [
        # Hors périmètre technique
        "mobile app", "flutter", "react native", "ios", "android",
        "machine learning", "data science", "devops", "blockchain",
        # Conditions défavorables
        "stagiaire", "bénévole", "gratuit", "sans rémunération",
        "cobol", "vb.net", "php legacy",
        # Missions anglophones (on veut FR uniquement)
        "looking for", "we are hiring", "job offer",
    ])
    MIN_BUDGET: int = 300
    PREFERRED_LANGS: List[str] = field(default_factory=lambda: ["fr"])

    # --- Texte profil idéal pour les embeddings sémantiques ---
    # Décrit précisément ce que tu cherches → meilleur scoring sémantique
    IDEAL_PROFILE_TEXT: str = os.getenv(
        "IDEAL_PROFILE_TEXT",
        "Développeur web freelance spécialisé WordPress et Shopify. "
        "Recherche missions de création de site vitrine, refonte de site existant, "
        "boutique en ligne WooCommerce ou Shopify, landing page. "
        "Missions en français uniquement, budget minimum 300€. "
        "Télétravail ou remote."
    )



    # --- Database ---
    # Sur Railway : DB_PATH=/app/data/missions.db (volume persistant)
    DB_PATH: str = os.getenv("DB_PATH", "data/missions.db")

    # --- Sources actives ---
    # Sélection optimisée pour missions FR création/refonte de site
    SOURCES_ENABLED: List[str] = field(default_factory=lambda: [
        # ✅ Plateformes freelance FR — sources primaires
        "codeur",          # codeur.com — meilleure source FR
        "malt",            # malt.fr — missions vitrine/refonte
        "remixjobs",       # flux RSS FR
        "welovedevs",      # offres FR remote
        "freelance.com",   # freelance.com FR
        "404works",        # 404works — missions web FR
        "comeup",          # comeup.com — marketplace FR
        "befreelancr",     # befreelancr.com — FR
        "collective.work", # collective.work — FR
        "kicklox",         # kicklox — tech FR
        "cremedelacreme",  # Crème de la Crème — missions premium senior
        # ✅ Job boards FR
        "indeed.fr",       # Indeed France — RSS freelance
        "welcomejungle",   # Welcome to the Jungle
        # ✅ Annonces généralistes FR
        "5euros",          # 5euros.com — micro-services FR
        "paruvendu",       # ParuVendu — services informatique
        # ✅ Forums FR (demandes sans passer par plateformes)
        "webrankseo",      # Forum WebRankSEO — SEO/web FR
        "hardware.fr",     # Forum Hardware.fr — emploi IT
        # ✅ Sources mixtes avec filtre FR
        "linkedin",        # LinkedIn — missions FR
        "reddit",          # r/forhire filtre FR
        # ✅ Startups & communautés internationales
        "wellfound",       # Wellfound (ex-AngelList) — startups FR
        "producthunt",     # Product Hunt — lancements startups
        "indiehackers",    # Indie Hackers — makers FR
        # ✅ Sources configurables
        "rss.custom",      # flux RSS perso (configurable)
        # ⚠️  Activer prudemment (anti-bot agressif ou quota limité)
        # "leboncoin",       # Leboncoin — anti-bot fort
        # "stackoverflow.fr",# Stack Overflow — quota API 300/jour sans clé
        # ⚠️  Facebook : nécessite FB_ENABLED=true + cookies valides
        # "facebook.groups",
        # ❌ Désactivées — majoritairement EN
        # "upwork", "remoteok", "freelancer.com", "fiverr", "toptal",
        # "hackernews", "dev.to", "twitter", "github.jobs",
    ])

    # --- Credentials réseaux sociaux ---
    TWITTER_BEARER_TOKEN: str = os.getenv("TWITTER_BEARER_TOKEN", "")

    # --- Facebook Groups (sources/facebook_groups.py) ---
    # FB_ENABLED=true pour activer (nécessite cookies valides)
    # FB_COOKIES_PATH=/app/data/fb_cookies.json
    # Procédure init : python -m sources.facebook_groups --login

    # --- Stack Overflow API (optionnel) ---
    # Sans clé : 300 req/jour  |  Avec clé : 10 000 req/jour
    # STACKOVERFLOW_API_KEY=xxxxx (inscris-toi sur stackapps.com)

    # --- Bot Telegram bidirectionnel ---
    # True = polling actif en parallèle de la boucle principale
    TELEGRAM_BOT_ENABLED: bool = os.getenv("TELEGRAM_BOT_ENABLED", "true").lower() == "true"

    # --- Scoring sémantique ---
    # True = utilise les embeddings OpenAI pour un bonus de score
    SEMANTIC_SCORING_ENABLED: bool = os.getenv("SEMANTIC_SCORING", "true").lower() == "true"

    # --- RSS custom (sources supplémentaires) ---
    # Liste d'URLs de flux RSS à scraper en plus des sources standard
    CUSTOM_RSS_FEEDS: List[str] = field(default_factory=lambda: [
        # Exemples :
        # "https://monblog.fr/feed",
        # "https://autresite.com/jobs.rss",
    ])

settings = Settings()
