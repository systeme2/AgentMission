# =============================================================
# agents/scorer.py — scoring intelligent multi-critères
# =============================================================

from config.settings import settings
from core.memory import apply_memory_to_score
from agents.semantic_scorer import semantic_score_bonus


async def score_job(job: dict) -> dict:
    """
    Score entre 0.0 et 1.0.
    Enrichit le job d'une clé 'score' et 'score_detail'.
    """
    text = (job.get("title", "") + " " + job.get("description", "")).lower()
    analysis = job.get("analysis", {})

    score = 0.0
    detail = {}

    # ── 1. Mots-clés positifs ────────────────────────────────
    keyword_hits = []
    for kw in settings.PREFERRED_KEYWORDS:
        if kw.lower() in text:
            keyword_hits.append(kw)

    kw_score = min(len(keyword_hits) * 0.12, 0.40)
    score += kw_score
    detail["keywords"] = {"hits": keyword_hits, "score": round(kw_score, 3)}

    # ── 2. Mots-clés négatifs ────────────────────────────────
    neg_hits = [kw for kw in settings.NEGATIVE_KEYWORDS if kw.lower() in text]
    neg_penalty = len(neg_hits) * 0.15
    score -= neg_penalty
    detail["negative"] = {"hits": neg_hits, "penalty": round(neg_penalty, 3)}

    # ── 3. Budget ────────────────────────────────────────────
    budget = analysis.get("budget_estime", 0)
    if not budget:
        budget = _parse_budget_raw(job.get("budget_raw", ""))

    if budget >= settings.MIN_BUDGET * 2:
        budget_score = 0.25
    elif budget >= settings.MIN_BUDGET:
        budget_score = 0.15
    elif budget > 0:
        budget_score = 0.05
    else:
        budget_score = 0.05  # neutre si pas d'info
    score += budget_score
    detail["budget"] = {"value": budget, "score": budget_score}

    # ── 4. Remote ────────────────────────────────────────────
    remote = analysis.get("remote")
    if remote is True:
        score += 0.10
        detail["remote"] = True
    else:
        detail["remote"] = False

    # ── 5. Langue préférée ───────────────────────────────────
    lang = analysis.get("langue", "")

    # Détection FR directe dans le texte brut (si l'analyse IA n'est pas dispo)
    fr_markers = ["recherche", "besoin", "mission", "développeur", "prestataire",
                  "site web", "vitrine", "refonte", "création", "boutique"]
    en_markers = ["looking for", "we need", "hiring", "developer wanted",
                  "remote position", "job offer", "apply now"]
    text_has_fr = any(m in text for m in fr_markers)
    text_has_en = any(m in text for m in en_markers)

    if lang in settings.PREFERRED_LANGS or (not lang and text_has_fr and not text_has_en):
        score += 0.10   # boost FR renforcé
        detail["lang"] = "fr"
    elif lang and lang not in settings.PREFERRED_LANGS:
        score -= 0.30   # pénalité forte si langue détectée ≠ FR
        detail["lang"] = lang
    elif text_has_en and not text_has_fr:
        score -= 0.20   # pénalité si texte semble EN sans markers FR
        detail["lang"] = "en?"
    else:
        detail["lang"] = lang or "?"

    # ── 6. C'est bien du freelance ? ─────────────────────────
    if not analysis.get("est_freelance", True):
        score -= 0.20
        detail["est_freelance"] = False
    else:
        detail["est_freelance"] = True

    # ── 7. Stack match ───────────────────────────────────────
    detected_stack = analysis.get("stack", [])
    preferred_lower = [k.lower() for k in settings.PREFERRED_KEYWORDS]
    stack_hits = [s for s in detected_stack if s.lower() in preferred_lower]
    stack_score = min(len(stack_hits) * 0.05, 0.15)
    score += stack_score
    detail["stack"] = {"detected": detected_stack, "hits": stack_hits, "score": stack_score}

    # ── 8. Bonus sémantique (embeddings) ────────────────────
    sem_bonus = await semantic_score_bonus(job)
    score += sem_bonus
    detail["semantic_bonus"] = sem_bonus

    # ── 9. Mémoire utilisateur ───────────────────────────────
    base_score = round(min(max(score, 0.0), 1.0), 3)
    final_score = round(min(1.0, max(0.0, apply_memory_to_score(job, base_score))), 3)
    detail["memory_adjustment"] = round(final_score - base_score, 3)

    job["score"] = final_score
    job["score_detail"] = detail

    return job


def _parse_budget_raw(raw: str) -> int:
    import re
    if not raw:
        return 0
    m = re.search(r"(\d[\d\s]*)", raw)
    if m:
        try:
            return int(m.group(1).replace(" ", ""))
        except ValueError:
            return 0
    return 0
