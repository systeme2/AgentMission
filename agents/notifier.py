# =============================================================
# agents/notifier.py — envoi Telegram avec messages riches
# =============================================================

import requests
from config.settings import settings
from core.telegram_bot import make_job_keyboard, register_job_url


def _score_emoji(score: float) -> str:
    if score >= 0.8:
        return "🔥🔥🔥"
    elif score >= 0.6:
        return "🔥🔥"
    elif score >= 0.4:
        return "✅"
    else:
        return "📌"


def _source_emoji(source: str) -> str:
    emojis = {
        "codeur": "🖥️",
        "reddit": "💬",
        "welovedevs": "❤️",
        "remixjobs": "🎵",
        "malt": "🍺",
        "upwork": "🌐",
    }
    for key, emoji in emojis.items():
        if key in source:
            return emoji
    return "📡"


def _build_message(job: dict, profile_label: str = "") -> str:
    score = job.get("score", 0)
    analysis = job.get("analysis", {})
    detail = job.get("score_detail", {})

    score_pct = int(score * 100)
    emoji = _score_emoji(score)
    src_emoji = _source_emoji(job.get("source", ""))

    # Résumé IA ou titre
    resume = analysis.get("resume") or job.get("title", "")[:100]

    # Stack détectée
    stack = analysis.get("stack", [])
    stack_str = " • ".join(f"`{t}`" for t in stack[:5]) if stack else "_non détectée_"

    # Budget
    budget = analysis.get("budget_estime", 0)
    budget_str = f"{budget}€" if budget else "_non précisé_"

    # Remote
    remote = analysis.get("remote")
    remote_str = "✅ Oui" if remote else ("❌ Non" if remote is False else "❓")

    # Mots-clés qui ont matché
    kw_hits = detail.get("keywords", {}).get("hits", [])
    kw_str = " ".join(f"#{k}" for k in kw_hits[:5]) if kw_hits else ""

    profile_tag = f"\n🎯 *Profil :* {profile_label}" if profile_label else ""
    message = f"""{emoji} *Nouvelle mission — {score_pct}%*{profile_tag}

{src_emoji} *Source :* {job.get('source', '?')}
📋 *Titre :* {job.get('title', '')[:120]}

💬 _{resume}_

🛠 *Stack :* {stack_str}
💰 *Budget :* {budget_str}
🏠 *Remote :* {remote_str}
{kw_str}

🔗 [Voir la mission]({job.get('url', '#')})"""

    return message


def send_alert(job: dict, profile_label: str = "") -> bool:
    """Envoie une alerte Telegram avec boutons inline. Retourne True si succès."""
    try:
        message = _build_message(job, profile_label=profile_label)
        job_url = job.get("url", "")

        # Enregistre l'URL pour les callbacks de boutons
        if job_url:
            register_job_url(job_url)

        # Chat ID : profil peut avoir son propre canal
        chat_id = job.get("_profile_chat_id") or settings.TELEGRAM_CHAT_ID
        tg_url  = f"https://api.telegram.org/bot{settings.TELEGRAM_TOKEN}/sendMessage"

        # Boutons inline 👍 👎 📝
        keyboard = make_job_keyboard(job_url) if job_url else None

        payload = {
            "chat_id":                  chat_id,
            "text":                     message,
            "parse_mode":               "Markdown",
            "disable_web_page_preview": False,
        }
        if keyboard:
            import json
            payload["reply_markup"] = json.dumps(keyboard)

        resp = requests.post(tg_url, data=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if data.get("ok"):
            print(f"  📲 Telegram envoyé : {job['title'][:60]} ({int(job.get('score',0)*100)}%)")
            return True
        else:
            print(f"  ❌ Telegram erreur: {data.get('description')}")
            return False

    except Exception as e:
        print(f"  ❌ Telegram exception: {e}")
        return False


def send_summary(stats: dict):
    """Envoie un résumé périodique."""
    try:
        msg = f"""📊 *Rapport agent missions*

🔎 Total scrappées : {stats.get('total', 0)}
📲 Envoyées : {stats.get('sent', 0)}
💚 Likées : {stats.get('liked', 0)}

*Par source :*
{chr(10).join(f"  • {k}: {v}" for k, v in stats.get('by_source', {}).items())}"""

        url = f"https://api.telegram.org/bot{settings.TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={
            "chat_id": settings.TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "Markdown",
        }, timeout=10)

    except Exception as e:
        print(f"  ❌ Résumé Telegram: {e}")


def test_telegram() -> bool:
    """Vérifie que le bot Telegram fonctionne."""
    try:
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_TOKEN}/sendMessage"
        resp = requests.post(url, data={
            "chat_id": settings.TELEGRAM_CHAT_ID,
            "text": "🤖 *Agent missions démarré !* Je vais te trouver des missions 🚀",
            "parse_mode": "Markdown",
        }, timeout=10)
        return resp.json().get("ok", False)
    except Exception:
        return False
