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
        "wordpress", "react", "nextjs", "seo", "vitrine",
        "refonte", "site web", "frontend", "freelance", "développeur"
    ])
    NEGATIVE_KEYWORDS: List[str] = field(default_factory=lambda: [
        "php legacy", "cobol", "vb.net", "stagiaire", "bénévole"
    ])
    MIN_BUDGET: int = 200
    PREFERRED_LANGS: List[str] = field(default_factory=lambda: ["fr"])

    # --- Texte profil idéal pour les embeddings sémantiques ---
    # Si vide → auto-généré depuis PREFERRED_KEYWORDS
    IDEAL_PROFILE_TEXT: str = os.getenv("IDEAL_PROFILE_TEXT", "")

    # --- Database ---
    # Sur Railway : DB_PATH=/app/data/missions.db (volume persistant)
    DB_PATH: str = os.getenv("DB_PATH", "data/missions.db")

    # --- Sources actives ---
    SOURCES_ENABLED: List[str] = field(default_factory=lambda: [
        # Phase 0
        "codeur", "reddit", "remixjobs", "welovedevs",
        # Phase 1
        "freelance.com", "404works", "comeup", "befreelancr", "collective.work",
        # Phase 2
        "malt", "upwork", "remoteok", "freelancer.com",
        "fiverr", "toptal", "kicklox",
        # Phase 3
        "hackernews", "dev.to", "linkedin", "twitter", "indiehackers",
        # Nouvelles sources
        "github.jobs", "rss.custom",
    ])

    # --- Credentials réseaux sociaux ---
    TWITTER_BEARER_TOKEN: str = os.getenv("TWITTER_BEARER_TOKEN", "")

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
