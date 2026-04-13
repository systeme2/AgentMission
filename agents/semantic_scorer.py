# =============================================================
# agents/semantic_scorer.py — scoring sémantique par embeddings
# =============================================================
#
# Complète le scorer mots-clés existant avec une similarité
# cosinus entre la description du job et le profil idéal de
# l'utilisateur (défini dans settings.IDEAL_PROFILE_TEXT).
#
# Stack :
#   - OpenAI text-embedding-3-small (1536 dims, ~$0.00002/1k tokens)
#   - Cache SQLite pour ne pas re-calculer l'embedding du profil
#   - Fallback silencieux si pas de clé API
#
# Le semantic score est un BONUS (0.0–0.20) ajouté au score
# mots-clés existant — il ne le remplace pas.
# =============================================================

import asyncio
import json
import math
import hashlib
from config.settings import settings

# Cache en mémoire des embeddings déjà calculés (url → embedding)
_embedding_cache: dict = {}
# Embedding du profil idéal (calculé une seule fois)
_profile_embedding: list | None = None


# ── Calcul cosinus ────────────────────────────────────────────

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Similarité cosinus entre deux vecteurs."""
    dot  = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── Appel API OpenAI embeddings ───────────────────────────────

def _get_embedding_sync(text: str) -> list[float] | None:
    """Calcule l'embedding d'un texte via OpenAI API (synchrone)."""
    if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY.startswith("sk-..."):
        return None
    try:
        import openai
        openai.api_key = settings.OPENAI_API_KEY
        resp = openai.embeddings.create(
            model="text-embedding-3-small",
            input=text[:8000],  # limite tokens
        )
        return resp.data[0].embedding
    except Exception as exc:
        print(f"  ⚠️  [SemanticScorer] embedding API: {exc}")
        return None


async def _get_embedding(text: str) -> list[float] | None:
    """Version async — délègue à asyncio.to_thread pour ne pas bloquer."""
    cache_key = hashlib.md5(text.encode()).hexdigest()
    if cache_key in _embedding_cache:
        return _embedding_cache[cache_key]

    emb = await asyncio.to_thread(_get_embedding_sync, text)
    if emb:
        _embedding_cache[cache_key] = emb
    return emb


async def _get_profile_embedding() -> list[float] | None:
    """Retourne l'embedding du profil idéal (mis en cache)."""
    global _profile_embedding
    if _profile_embedding is not None:
        return _profile_embedding

    profile_text = getattr(settings, "IDEAL_PROFILE_TEXT", None)
    if not profile_text:
        # Construire automatiquement depuis les keywords
        kw = ", ".join(settings.PREFERRED_KEYWORDS)
        profile_text = (
            f"Freelance développeur web expert en {kw}. "
            f"Recherche missions remote, budget minimum {settings.MIN_BUDGET}€. "
            f"Spécialités : développement web, refonte site, SEO, React, WordPress."
        )

    _profile_embedding = await _get_embedding(profile_text)
    return _profile_embedding


# ── Score sémantique ──────────────────────────────────────────

async def semantic_score_bonus(job: dict) -> float:
    """
    Retourne un bonus sémantique entre 0.0 et 0.20.
    Retourne 0.0 si pas de clé API ou si l'API échoue.
    """
    if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY.startswith("sk-..."):
        return 0.0

    try:
        # Texte du job à embedder
        job_text = (
            f"{job.get('title', '')} "
            f"{job.get('description', '')[:500]} "
            f"{' '.join(job.get('analysis', {}).get('stack', []))}"
        ).strip()

        if not job_text:
            return 0.0

        # Calculer les deux embeddings en parallèle
        job_emb, profile_emb = await asyncio.gather(
            _get_embedding(job_text),
            _get_profile_embedding(),
        )

        if job_emb is None or profile_emb is None:
            return 0.0

        # Similarité cosinus → bonus entre 0.0 et 0.20
        similarity = _cosine_similarity(job_emb, profile_emb)
        # La similarité cosinus est entre -1 et 1 → on la ramène à [0, 0.20]
        # Une similarité > 0.7 = très pertinent → bonus max
        bonus = min(max(similarity, 0.0), 1.0) * 0.20
        return round(bonus, 4)

    except Exception as exc:
        print(f"  ⚠️  [SemanticScorer] score_bonus: {exc}")
        return 0.0


def clear_cache():
    """Vide le cache des embeddings (utile pour les tests)."""
    global _embedding_cache, _profile_embedding
    _embedding_cache    = {}
    _profile_embedding  = None
