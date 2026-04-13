# =============================================================
# config/profiles.py — Système multi-profils
# =============================================================
#
# Un "profil" = un ensemble de préférences pour un type de
# mission précis. Tu peux définir autant de profils que tu veux.
#
# Chaque profil a :
#   name              → identifiant unique
#   label             → nom affiché dans les notifs
#   keywords          → mots-clés positifs
#   negative_keywords → mots-clés à éviter
#   min_budget        → budget minimum
#   min_score         → seuil de notification
#   preferred_langs   → langues préférées
#   telegram_chat_id  → peut pointer vers un channel/topic différent
#   ideal_profile_text→ texte libre pour les embeddings sémantiques
#   sources_override  → si défini, surcharge SOURCES_ENABLED pour ce profil
#
# Le profil actif est défini par ACTIVE_PROFILE dans settings.
# "all" = aucun filtre de profil (comportement historique).
# =============================================================

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Profile:
    name:               str
    label:              str
    keywords:           List[str]
    negative_keywords:  List[str]   = field(default_factory=list)
    min_budget:         int         = 200
    min_score:          float       = 0.4
    preferred_langs:    List[str]   = field(default_factory=lambda: ["fr"])
    telegram_chat_id:   Optional[str] = None   # None = utilise le chat_id global
    ideal_profile_text: Optional[str] = None   # None = auto-généré depuis keywords
    sources_override:   Optional[List[str]] = None  # None = toutes les sources


# ── Profils prédéfinis ────────────────────────────────────────

PROFILES: dict[str, Profile] = {

    # Profil généraliste (comportement historique)
    "all": Profile(
        name    = "all",
        label   = "Toutes missions",
        keywords= [
            "wordpress", "react", "nextjs", "seo", "vitrine",
            "refonte", "site web", "frontend", "freelance", "développeur",
        ],
        negative_keywords = ["php legacy", "cobol", "vb.net", "stagiaire", "bénévole"],
        min_budget= 200,
        min_score = 0.4,
    ),

    # Profil développeur WordPress
    "wordpress": Profile(
        name    = "wordpress",
        label   = "🔌 WordPress / WooCommerce",
        keywords= [
            "wordpress", "woocommerce", "elementor", "divi", "woo",
            "boutique en ligne", "e-commerce", "vitrine", "refonte site",
            "plugin", "thème", "gutenberg",
        ],
        negative_keywords = ["angular", "django", "rails", "cobol", "stagiaire"],
        min_budget= 300,
        min_score = 0.45,
        ideal_profile_text = (
            "Expert WordPress senior, spécialiste WooCommerce et Elementor. "
            "Refonte de sites vitrines et boutiques en ligne. "
            "Remote uniquement. Budget minimum 300€."
        ),
    ),

    # Profil développeur React / Next.js
    "react": Profile(
        name    = "react",
        label   = "⚛️ React / Next.js",
        keywords= [
            "react", "nextjs", "next.js", "typescript", "tailwind",
            "frontend", "composants", "spa", "dashboard", "application web",
            "api rest", "graphql", "vercel",
        ],
        negative_keywords = ["wordpress", "drupal", "joomla", "cobol", "stagiaire"],
        min_budget= 400,
        min_score = 0.5,
        ideal_profile_text = (
            "Développeur React / Next.js senior, TypeScript, Tailwind. "
            "Spécialiste applications web modernes, SPA, dashboards. "
            "Remote, missions longue durée préférées. Budget minimum 400€."
        ),
    ),

    # Profil SEO technique
    "seo": Profile(
        name    = "seo",
        label   = "📈 SEO Technique",
        keywords= [
            "seo", "référencement", "audit seo", "core web vitals",
            "optimisation", "google", "analytics", "search console",
            "netlinking", "contenu", "mots-clés", "balises",
        ],
        negative_keywords = ["cobol", "stagiaire", "bénévole"],
        min_budget= 250,
        min_score = 0.45,
        ideal_profile_text = (
            "Expert SEO technique et éditorial. Audits SEO complets, "
            "optimisation Core Web Vitals, stratégie de contenu. "
            "Budget minimum 250€."
        ),
    ),

    # Profil international (Upwork, Remote OK, anglophone)
    "international": Profile(
        name    = "international",
        label   = "🌍 International (EN)",
        keywords= [
            "react", "nextjs", "typescript", "node", "python",
            "remote", "fullstack", "developer", "engineer", "freelance",
            "web app", "saas", "api",
        ],
        negative_keywords = ["onsite", "office only", "no remote", "stagiaire"],
        min_budget= 500,
        min_score = 0.5,
        preferred_langs = ["en"],
        ideal_profile_text = (
            "Senior full-stack developer, React/Next.js, TypeScript, Node.js. "
            "Remote only, international clients. Minimum budget $500."
        ),
        sources_override = [
            "upwork", "remoteok", "freelancer.com",
            "hackernews", "reddit", "linkedin",
        ],
    ),
}


def get_profile(name: str) -> Profile:
    """Retourne le profil par nom, ou le profil 'all' par défaut."""
    return PROFILES.get(name, PROFILES["all"])


def list_profiles() -> list[str]:
    return list(PROFILES.keys())
