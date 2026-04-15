# =============================================================
# agents/analyzer.py — analyse IA via OpenAI
# =============================================================

import json
import asyncio
import openai
from config.settings import settings

openai.api_key = settings.OPENAI_API_KEY


# Compat: certains environnements ont une combinaison openai/httpx qui casse
# l'initialisation du proxy lazy `openai.chat` (TypeError sur `proxies`).
# On installe un stub minimal pour permettre les tests/mocks (`patch`) et
# garder un fallback propre côté analyse.
try:
    _ = openai.chat.completions
except Exception:
    class _CompatCompletions:
        def create(self, *args, **kwargs):
            raise RuntimeError("OpenAI client unavailable in this environment")

    class _CompatChat:
        completions = _CompatCompletions()

    openai.chat = _CompatChat()


SYSTEM_PROMPT = """Tu es un assistant expert en analyse de missions freelance tech.
Tu analyses les offres de mission et retournes UNIQUEMENT un JSON valide, sans markdown ni explication.
"""

ANALYSIS_PROMPT = """Analyse cette mission freelance et retourne un JSON strict avec ces champs :

{
  "type": "web | mobile | data | design | autre",
  "stack": ["liste", "des", "technologies"],
  "budget_estime": 0,
  "niveau": "débutant | intermédiaire | expert",
  "remote": true | false | null,
  "resume": "résumé en 1 phrase claire",
  "est_freelance": true | false,
  "langue": "fr | en | autre"
}

Titre: {title}
Description: {description}

Retourne UNIQUEMENT le JSON."""


async def analyze_job(job: dict) -> dict:
    """Analyse une mission avec GPT. Retourne le job enrichi d'une clé 'analysis'."""

    # Si pas de clé OpenAI → analyse basique sans IA
    if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY.startswith("sk-..."):
        job["analysis"] = _basic_analysis(job)
        return job

    try:
        prompt = ANALYSIS_PROMPT.format(
            title=job.get("title", ""),
            description=job.get("description", "")[:500],
        )

        response = await asyncio.to_thread(
            lambda: openai.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=200,
                temperature=0.1,
            )
        )

        raw = response.choices[0].message.content.strip()

        # Nettoyer les éventuels markdown fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        analysis = json.loads(raw)
        job["analysis"] = analysis

    except json.JSONDecodeError as e:
        print(f"  ⚠️  Analyzer: JSON invalide — {e}")
        job["analysis"] = _basic_analysis(job)

    except Exception as e:
        print(f"  ⚠️  Analyzer: erreur IA — {e}")
        job["analysis"] = _basic_analysis(job)

    return job


def _basic_analysis(job: dict) -> dict:
    """Fallback si pas d'OpenAI : analyse par mots-clés."""
    text = (job.get("title", "") + " " + job.get("description", "")).lower()

    stack = []
    tech_keywords = [
        "wordpress", "react", "vue", "angular", "nextjs", "laravel",
        "python", "django", "fastapi", "node", "express", "php",
        "flutter", "swift", "kotlin", "figma", "seo", "shopify"
    ]
    for tech in tech_keywords:
        if tech in text:
            stack.append(tech)

    return {
        "type": "web" if any(k in text for k in ["web", "site", "app"]) else "autre",
        "stack": stack,
        "budget_estime": _extract_budget(text),
        "niveau": "intermédiaire",
        "remote": "remote" in text or "télétravail" in text or "à distance" in text,
        "resume": job.get("title", "")[:100],
        "est_freelance": True,
        "langue": "fr" if any(w in text for w in ["recherche", "besoin", "mission"]) else "en",
    }


def _extract_budget(text: str) -> int:
    """Tente d'extraire un budget depuis le texte."""
    import re
    # Cherche des patterns comme "500€", "1000 euros", "$800"
    patterns = [
        r"(\d[\d\s]*)\s*€",
        r"(\d[\d\s]*)\s*euro",
        r"\$(\d[\d\s]*)",
        r"budget[^\d]*(\d+)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                return int(m.group(1).replace(" ", ""))
            except ValueError:
                pass
    return 0
