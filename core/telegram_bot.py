# =============================================================
# core/telegram_bot.py — Bot Telegram bidirectionnel
# =============================================================
#
# Le bot reçoit des messages et callbacks depuis Telegram et
# réagit en temps réel :
#
# Commandes disponibles :
#   /start   → message de bienvenue
#   /stats   → statistiques courantes
#   /top5    → 5 meilleures missions non vues
#   /pause X → met en pause l'agent pour X minutes
#   /resume  → reprend l'agent si en pause
#   /status  → état de l'agent (actif / en pause)
#   /seuil X → change le MIN_SCORE à la volée (ex: /seuil 0.5)
#
# Callbacks sur les boutons inline des notifications :
#   👍  → like  (record_like  + update_status 'liked')
#   👎  → dislike (record_dislike + update_status 'disliked')
#   📝  → postuler (update_status 'applied')
#
# Le notifier enrichit chaque message avec des boutons inline.
# Le bot tourne en parallèle de la boucle principale via
# asyncio.create_task() dans main.py.
# =============================================================

import asyncio
import json
import re
import requests
from datetime import datetime, timedelta
from config.settings import settings
from core.database import get_stats, get_all_missions, update_status, save_feedback
from core.memory import record_like, record_dislike

BASE_URL = f"https://api.telegram.org/bot{settings.TELEGRAM_TOKEN}"

# État global de l'agent (partagé avec orchestrator via ce module)
_agent_state = {
    "paused":     False,
    "pause_until": None,   # datetime ou None
    "last_update_id": 0,
}


# ── Getters d'état ────────────────────────────────────────────

def is_paused() -> bool:
    """Retourne True si l'agent est en pause."""
    if not _agent_state["paused"]:
        return False
    until = _agent_state.get("pause_until")
    if until and datetime.now() >= until:
        # La pause a expiré → reprendre automatiquement
        _agent_state["paused"]     = False
        _agent_state["pause_until"] = None
        return False
    return True


def get_state() -> dict:
    return dict(_agent_state)


# ── API Telegram helpers ──────────────────────────────────────

def _api(method: str, payload: dict = None, timeout: int = 10) -> dict:
    """Appel générique à l'API Telegram."""
    try:
        resp = requests.post(
            f"{BASE_URL}/{method}",
            json=payload or {},
            timeout=timeout,
        )
        return resp.json()
    except Exception as exc:
        print(f"  ❌ [TelegramBot] {method}: {exc}")
        return {"ok": False}


def _send(chat_id: str, text: str, reply_markup: dict = None, parse_mode: str = "Markdown"):
    payload = {
        "chat_id":    chat_id,
        "text":       text,
        "parse_mode": parse_mode,
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    return _api("sendMessage", payload)


def _answer_callback(callback_id: str, text: str = ""):
    _api("answerCallbackQuery", {"callback_query_id": callback_id, "text": text})


def _edit_message(chat_id: str, message_id: int, text: str, reply_markup: dict = None):
    payload = {
        "chat_id":    chat_id,
        "message_id": message_id,
        "text":       text,
        "parse_mode": "Markdown",
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    _api("editMessageText", payload)


# ── Boutons inline pour les notifications ────────────────────

def make_job_keyboard(job_url: str) -> dict:
    """
    Crée les boutons 👍 👎 📝 pour une notification de mission.
    Le callback_data encode l'action + l'URL hashée (tronquée).
    """
    # On encode l'URL dans le callback (max 64 chars Telegram)
    url_hash = str(abs(hash(job_url)))[:12]
    return {
        "inline_keyboard": [[
            {"text": "👍 Intéressant",  "callback_data": f"like:{url_hash}"},
            {"text": "👎 Pas pour moi", "callback_data": f"dislike:{url_hash}"},
            {"text": "📝 J'postule",    "callback_data": f"apply:{url_hash}"},
        ]]
    }


# Mapping url_hash → url pour les callbacks
_url_registry: dict = {}


def register_job_url(url: str):
    """Enregistre l'URL pour retrouver le job depuis un callback."""
    url_hash = str(abs(hash(url)))[:12]
    _url_registry[url_hash] = url


def get_url_from_hash(url_hash: str) -> str | None:
    return _url_registry.get(url_hash)


# ── Handlers de commandes ─────────────────────────────────────

def _handle_start(chat_id: str):
    msg = """🤖 *Mission Agent v2 — Bot bidirectionnel*

Je scrape 23 sources pour te trouver des missions freelance.

*📋 Consulter les missions :*
/top5       → 5 meilleures missions (par score)
/dernieres  → 10 dernières missions reçues

*📊 Statistiques & contrôle :*
/stats      → statistiques globales
/status     → état de l'agent
/pause 60   → pause 60 minutes
/resume     → reprendre maintenant
/seuil 0.5  → changer le seuil de score

*Sur chaque notification :*
👍 → like  👎 → pas pour moi  📝 → postulée

*🆘 Dépannage :*
/monid → affiche ton chat\_id (utile si accès refusé)"""
    _send(chat_id, msg)


def _handle_stats(chat_id: str):
    stats = get_stats()
    by_src = "\n".join(f"  • {k}: {v}" for k, v in
                        sorted(stats["by_source"].items(), key=lambda x: -x[1])[:8])
    msg = f"""📊 *Statistiques Mission Agent*

🔎 Total missions vues   : *{stats['total']}*
📲 Notifications envoyées: *{stats['sent']}*
💚 Missions likées       : *{stats['liked']}*

*Top sources :*
{by_src}"""
    _send(chat_id, msg)


def _handle_top5(chat_id: str):
    """Top 5 missions par score parmi les 50 dernières notifiées."""
    missions = get_all_missions(limit=50)
    top = sorted(
        [m for m in missions if m.get("score", 0) > 0],
        key=lambda m: m.get("score", 0),
        reverse=True,
    )[:5]

    if not top:
        _send(chat_id,
              "📭 Aucune mission en base.\n\n"
              "L\'agent n\'a peut-être pas encore complété un cycle. "
              "Tape /status pour vérifier.")
        return

    lines = []
    for i, m in enumerate(top, 1):
        score_pct = int((m.get("score") or 0) * 100)
        title     = (m.get("title") or "")[:55]
        source    = m.get("source", "?")
        status    = m.get("status", "?")
        url       = m.get("url", "#")
        status_icon = {"sent": "📲", "liked": "💚", "disliked": "🔴",
                       "applied": "📝", "new": "🆕"}.get(status, "•")
        lines.append(
            f"{i}. {status_icon} *{title}*\n"
            f"   {source} — {score_pct}% — [Voir la mission]({url})"
        )

    _send(chat_id, "🏆 *Top 5 missions (score le plus élevé) :*\n\n" + "\n\n".join(lines))


def _handle_dernieres(chat_id: str):
    """10 dernières missions reçues, dans l\'ordre chronologique inverse."""
    missions = get_all_missions(limit=10)

    if not missions:
        _send(chat_id,
              "📭 Aucune mission en base.\n\n"
              "L\'agent n\'a peut-être pas encore complété un cycle. "
              "Tape /status pour vérifier l\'état.")
        return

    lines = []
    for m in missions:
        score_pct  = int((m.get("score") or 0) * 100)
        title      = (m.get("title") or "")[:55]
        source     = m.get("source", "?")
        status     = m.get("status", "?")
        url        = m.get("url", "#")
        created    = (m.get("created_at") or "")[:16].replace("T", " ")
        status_icon = {"sent": "📲", "liked": "💚", "disliked": "🔴",
                       "applied": "📝", "new": "🆕"}.get(status, "•")
        lines.append(
            f"{status_icon} *{title}*\n"
            f"   {source} — {score_pct}% — {created} — [Voir]({url})"
        )

    _send(chat_id, "📋 *10 dernières missions :*\n\n" + "\n\n".join(lines))


def _handle_status(chat_id: str):
    if is_paused():
        until = _agent_state.get("pause_until")
        until_str = until.strftime("%H:%M") if until else "?"
        _send(chat_id, f"⏸ *Agent en pause* jusqu'à {until_str}")
    else:
        _send(chat_id, "▶️ *Agent actif* — scrape toutes les 5 min")


def _handle_pause(chat_id: str, minutes: int):
    if minutes <= 0 or minutes > 1440:  # max 24h
        _send(chat_id, "❌ Durée invalide (1–1440 minutes)")
        return
    _agent_state["paused"]      = True
    _agent_state["pause_until"] = datetime.now() + timedelta(minutes=minutes)
    _send(chat_id, f"⏸ *Agent mis en pause* pour {minutes} min.")


def _handle_resume(chat_id: str):
    _agent_state["paused"]      = False
    _agent_state["pause_until"] = None
    _send(chat_id, "▶️ *Agent repris !*")


def _handle_seuil(chat_id: str, value: float):
    if not 0.1 <= value <= 0.95:
        _send(chat_id, "❌ Seuil invalide (0.1–0.95)")
        return
    settings.MIN_SCORE = value
    _send(chat_id, f"✅ Seuil mis à jour : *{value:.0%}*\n(Prend effet au prochain cycle)")


# ── Handler de callbacks inline ───────────────────────────────

def _handle_callback(callback: dict):
    callback_id = callback.get("id", "")
    data        = callback.get("data", "")
    chat_id     = str(callback.get("message", {}).get("chat", {}).get("id", ""))
    message_id  = callback.get("message", {}).get("message_id")
    user        = callback.get("from", {}).get("first_name", "")

    if not data or not chat_id:
        return

    parts    = data.split(":", 1)
    action   = parts[0] if parts else ""
    url_hash = parts[1] if len(parts) > 1 else ""
    job_url  = get_url_from_hash(url_hash)

    if action == "like":
        if job_url:
            update_status(job_url, "liked")
            save_feedback(job_url, "liked")
            # Retrouver le job en base pour alimenter la mémoire
            missions = [m for m in get_all_missions(200) if m.get("url") == job_url]
            if missions:
                record_like(missions[0])
        _answer_callback(callback_id, "💚 Like enregistré !")
        if message_id:
            _edit_message_feedback(chat_id, message_id, "liked")

    elif action == "dislike":
        if job_url:
            update_status(job_url, "disliked")
            save_feedback(job_url, "disliked")
            missions = [m for m in get_all_missions(200) if m.get("url") == job_url]
            if missions:
                record_dislike(missions[0])
        _answer_callback(callback_id, "🔴 Dislike enregistré !")
        if message_id:
            _edit_message_feedback(chat_id, message_id, "disliked")

    elif action == "apply":
        if job_url:
            update_status(job_url, "applied")
            save_feedback(job_url, "applied")
        _answer_callback(callback_id, f"📝 Marqué comme postulé !")
        if message_id:
            _edit_message_feedback(chat_id, message_id, "applied")


def _edit_message_feedback(chat_id: str, message_id: int, action: str):
    """Remplace les boutons par un indicateur de statut."""
    labels = {"liked": "💚 Likée", "disliked": "🔴 Ignorée", "applied": "📝 Postulée"}
    label  = labels.get(action, "✅ Enregistré")
    # Supprime les boutons et ajoute le statut à la fin
    _api("editMessageReplyMarkup", {
        "chat_id":      chat_id,
        "message_id":   message_id,
        "reply_markup": json.dumps({"inline_keyboard": [[
            {"text": label, "callback_data": "noop"}
        ]]})
    })


# ── Dispatcher principal ──────────────────────────────────────

def _dispatch_update(update: dict):
    """Traite un update Telegram (message ou callback_query)."""
    # Callback inline (boutons 👍 👎 📝)
    if "callback_query" in update:
        _handle_callback(update["callback_query"])
        return

    # Message texte
    msg     = update.get("message", {})
    text    = (msg.get("text") or "").strip()
    chat_id = str(msg.get("chat", {}).get("id", ""))

    if not text or not chat_id:
        return

    # /monid répond à TOUT le monde sans auth — utile pour trouver son chat_id
    if text.lower().startswith("/monid"):
        _send(chat_id,
              f"🪪 *Ton chat\_id :* `{chat_id}`\n\n"
              f"Copie cette valeur dans la variable `TELEGRAM_CHAT_ID` de Railway.",
              parse_mode="Markdown")
        return

    # Sécurité : n'accepte que les messages de ton propre chat
    # Normalisation : strip() gère les espaces parasites dans les variables Railway
    allowed_id = str(settings.TELEGRAM_CHAT_ID).strip()
    if chat_id.strip() != allowed_id:
        print(f"  ⚠️  [TelegramBot] Message refusé de chat_id={chat_id!r} (attendu: {allowed_id!r})")
        _send(chat_id,
              f"⛔ *Accès refusé.*\n\n"
              f"🪪 Ton chat\_id : `{chat_id}`\n\n"
              f"Mets cette valeur dans la variable `TELEGRAM_CHAT_ID` sur Railway.",
              parse_mode="Markdown")
        return

    text_lower = text.lower()

    if text_lower.startswith("/start"):
        _handle_start(chat_id)

    elif text_lower.startswith("/stats"):
        _handle_stats(chat_id)

    elif text_lower.startswith("/top5"):
        _handle_top5(chat_id)

    elif text_lower.startswith("/dernieres") or text_lower.startswith("/dernières"):
        _handle_dernieres(chat_id)

    elif text_lower.startswith("/status"):
        _handle_status(chat_id)

    elif text_lower.startswith("/resume"):
        _handle_resume(chat_id)

    elif text_lower.startswith("/pause"):
        m = re.search(r"/pause\s+(\d+)", text_lower)
        if m:
            _handle_pause(chat_id, int(m.group(1)))
        else:
            _send(chat_id, "Usage : /pause 60 (minutes)")

    elif text_lower.startswith("/seuil"):
        m = re.search(r"/seuil\s+([\d.]+)", text_lower)
        if m:
            try:
                _handle_seuil(chat_id, float(m.group(1)))
            except ValueError:
                _send(chat_id, "Usage : /seuil 0.5")
        else:
            _send(chat_id, "Usage : /seuil 0.5")

    else:
        _send(chat_id, "❓ Commande inconnue. Tape /start pour voir les commandes.")


# ── Polling loop ──────────────────────────────────────────────

async def run_polling():
    """
    Polling long-polling Telegram.
    Tourne en tâche asyncio parallèle de la boucle principale.
    """
    print("📡 [TelegramBot] Polling démarré...")
    offset = _agent_state["last_update_id"] + 1

    while True:
        try:
            resp = await asyncio.to_thread(
                lambda: requests.get(
                    f"{BASE_URL}/getUpdates",
                    params={"offset": offset, "timeout": 30, "allowed_updates": ["message", "callback_query"]},
                    timeout=35,
                )
            )
            data = resp.json()

            if not data.get("ok"):
                await asyncio.sleep(5)
                continue

            updates = data.get("result", [])
            for update in updates:
                update_id = update.get("update_id", 0)
                if update_id >= offset:
                    offset = update_id + 1
                    _agent_state["last_update_id"] = update_id
                try:
                    _dispatch_update(update)
                except Exception as exc:
                    print(f"  ⚠️  [TelegramBot] dispatch: {exc}")

        except Exception as exc:
            print(f"  ⚠️  [TelegramBot] polling: {exc}")
            await asyncio.sleep(10)
