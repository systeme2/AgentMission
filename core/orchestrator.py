# =============================================================
# core/orchestrator.py — pipeline principal
# =============================================================

import asyncio
from agents.collector import collect_jobs, SOURCE_MAP
from agents.analyzer import analyze_job
from agents.scorer import score_job, quick_keyword_score
from agents.notifier import send_alert
from core.database import is_seen, is_title_hash_seen, save_mission, update_status, get_stats
from core.memory import get_preferences
from core.telegram_bot import is_paused
from config.settings import settings
from config.profiles import get_profile

# Limite max de jobs analysés par cycle (évite les pics de coût IA)
MAX_JOBS_PER_CYCLE = 50


async def run_pipeline(profile_name: str = None) -> dict:
    """
    Pipeline complet multi-profils :
    Collect → Filter seen → Analyze → Score → Notify
    profile_name: nom du profil à utiliser (None = settings.ACTIVE_PROFILE)
    Retourne des stats de la session.
    """
    # ── 0. Vérifier si en pause ───────────────────────────────
    if is_paused():
        print("⏸  Agent en pause — cycle ignoré")
        return {"collected": 0, "new": 0, "analyzed": 0, "sent": 0, "skipped": 0, "paused": True}

    # Charger le profil actif
    active_profile_name = profile_name or settings.ACTIVE_PROFILE
    profile = get_profile(active_profile_name)

    # Appliquer les overrides du profil sur les settings pour ce cycle
    original_keywords  = settings.PREFERRED_KEYWORDS[:]
    original_negkw     = settings.NEGATIVE_KEYWORDS[:]
    original_budget    = settings.MIN_BUDGET
    original_min_score = settings.MIN_SCORE
    original_langs     = settings.PREFERRED_LANGS[:]
    original_sources   = settings.SOURCES_ENABLED[:]

    if active_profile_name != "all":
        settings.PREFERRED_KEYWORDS = profile.keywords
        settings.NEGATIVE_KEYWORDS  = profile.negative_keywords
        settings.MIN_BUDGET         = profile.min_budget
        settings.MIN_SCORE          = profile.min_score
        settings.PREFERRED_LANGS    = profile.preferred_langs
        if profile.sources_override:
            settings.SOURCES_ENABLED = profile.sources_override
        if profile.ideal_profile_text:
            settings.IDEAL_PROFILE_TEXT = profile.ideal_profile_text
        print(f"🎯 Profil actif : [{profile.label}]")

    session = {"collected": 0, "new": 0, "analyzed": 0, "sent": 0, "skipped": 0,
               "profile": active_profile_name}

    # Définir la restauration ici pour pouvoir l'appeler sur tous les chemins
    def _restore():
        settings.PREFERRED_KEYWORDS = original_keywords
        settings.NEGATIVE_KEYWORDS  = original_negkw
        settings.MIN_BUDGET         = original_budget
        settings.MIN_SCORE          = original_min_score
        settings.PREFERRED_LANGS    = original_langs
        settings.SOURCES_ENABLED    = original_sources

    # ── 1. Collecte ──────────────────────────────────────────
    all_jobs = await collect_jobs()
    session["collected"] = len(all_jobs)

    if not all_jobs:
        print("😴 Aucune mission récupérée cette fois.")
        _restore()
        return session

    # ── 2. Filtrer les déjà vues (URL + title_hash cross-cycle) ─
    new_jobs = [
        j for j in all_jobs
        if not is_seen(j.get("url", ""))
        and not is_title_hash_seen(j.get("title_hash", ""))
    ]
    session["new"] = len(new_jobs)
    print(f"🆕 {len(new_jobs)} nouvelles missions (sur {len(all_jobs)} collectées)")

    if not new_jobs:
        print("👀 Tout a déjà été vu. Prochain cycle dans quelques minutes.")
        _restore()
        return session

    # ── 2b. Pré-filtrage rapide par mots-clés (sans IA) ──────
    # On trie par score rapide et on limite à MAX_JOBS_PER_CYCLE
    # pour éviter les pics de coût IA quand beaucoup de nouvelles missions arrivent.
    pre_scored = sorted(new_jobs, key=lambda j: quick_keyword_score(j), reverse=True)
    jobs_to_skip = [j for j in pre_scored if quick_keyword_score(j) < 0.05]
    jobs_to_analyze = [j for j in pre_scored if quick_keyword_score(j) >= 0.05]

    if jobs_to_skip:
        print(f"  ⏭️  {len(jobs_to_skip)} jobs ignorés avant IA (score rapide < 5%)")

    # Limite pour maîtriser les coûts IA
    if len(jobs_to_analyze) > MAX_JOBS_PER_CYCLE:
        print(f"  ✂️  Limite IA : {MAX_JOBS_PER_CYCLE}/{len(jobs_to_analyze)} jobs analysés")
        jobs_to_analyze = jobs_to_analyze[:MAX_JOBS_PER_CYCLE]

    new_jobs = jobs_to_analyze

    if not new_jobs:
        print("👀 Aucun job ne passe le pré-filtre mots-clés.")
        _restore()
        return session

    # ── 3. Analyse + Score en parallèle ─────────────────────
    print("\n🧠 Analyse en cours...")

    async def process_job(job):
        try:
            job = await analyze_job(job)
            job = await score_job(job)
            return job
        except Exception as e:
            print(f"  ❌ Erreur sur '{job.get('title', '?')[:40]}': {e}")
            return None

    # On limite à 5 en parallèle pour ne pas spammer l'API OpenAI
    semaphore = asyncio.Semaphore(5)

    async def process_with_sem(job):
        async with semaphore:
            return await process_job(job)

    results = await asyncio.gather(*[process_with_sem(j) for j in new_jobs])
    processed = [j for j in results if j is not None]
    session["analyzed"] = len(processed)

    # ── 4. Trier par score desc ──────────────────────────────
    processed.sort(key=lambda j: j.get("score", 0), reverse=True)

    # ── 5. Notifier si score suffisant ───────────────────────
    print(f"\n📲 Envoi des missions pertinentes (seuil: {settings.MIN_SCORE})...")

    for job in processed:
        score = job.get("score", 0)

        # Sauvegarde toujours
        is_new = save_mission(job)

        if not is_new:
            session["skipped"] += 1
            continue

        if score >= settings.MIN_SCORE:
            success = send_alert(job, profile_label=profile.label if active_profile_name != "all" else "")
            if success:
                update_status(job["url"], "sent")
                session["sent"] += 1
            await asyncio.sleep(0.5)  # Pas trop vite
        else:
            print(f"  ⏭️  Ignorée (score {int(score*100)}%) : {job['title'][:60]}")
            session["skipped"] += 1

    # ── 6. Restaurer settings originaux ─────────────────────
    _restore()

    # ── 7. Log de fin ────────────────────────────────────────
    print(f"\n✅ Session terminée [{profile.label}]:")
    print(f"   Collectées: {session['collected']}")
    print(f"   Nouvelles:  {session['new']}")
    print(f"   Analysées:  {session['analyzed']}")
    print(f"   Envoyées:   {session['sent']}")
    print(f"   Ignorées:   {session['skipped']}")

    return session
