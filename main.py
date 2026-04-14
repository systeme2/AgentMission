#!/usr/bin/env python3
# =============================================================
# main.py — point d'entrée principal
# =============================================================

import asyncio
import time
import sys
import argparse
from datetime import datetime

from core.database import init_db, get_stats, get_all_missions
from core.orchestrator import run_pipeline
from agents.notifier import send_summary, test_telegram
from config.settings import settings
from config.profiles import list_profiles, get_profile


async def _interruptible_sleep(seconds: int):
    """Sleep interruptible : se réveille si /interval ou /resume est reçu."""
    from core.telegram_bot import get_wakeup_event
    event = get_wakeup_event()
    if event is None:
        await asyncio.sleep(seconds)
        return
    event.clear()
    try:
        await asyncio.wait_for(event.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass  # timeout normal


def print_banner():
    print("""
╔══════════════════════════════════════════════╗
║        🤖  MISSION AGENT  v3.0              ║
║  28 sources · Multi-profils · Telegram bot  ║
╚══════════════════════════════════════════════╝
""")


def print_status():
    stats = get_stats()
    print(f"""
📊 Statistiques:
  Total missions vues   : {stats['total']}
  Notifications envoyées: {stats['sent']}
  Missions likées       : {stats['liked']}
  Par source            : {stats['by_source']}
""")


async def run_once():
    """Lance le pipeline une seule fois."""
    print(f"⏰ {datetime.now().strftime('%H:%M:%S')} — Lancement du pipeline...")
    await run_pipeline()


async def run_loop(profile: str = None):
    """Boucle infinie toutes les N minutes, avec bot Telegram en parallèle."""
    profile = profile or settings.ACTIVE_PROFILE
    print(f"🔁 Mode boucle — profil [{profile}] — cycle toutes les {settings.LOOP_INTERVAL}s")

    # Lancer le bot Telegram en tâche de fond si activé
    bot_task = None
    if settings.TELEGRAM_BOT_ENABLED:
        from core.telegram_bot import run_polling
        bot_task = asyncio.create_task(run_polling())
        print("🤖 Bot Telegram bidirectionnel démarré")

    cycle = 0
    try:
        while True:
            cycle += 1
            print(f"\n{'='*50}")
            print(f"🔄 CYCLE #{cycle} — {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
            print(f"{'='*50}")

            await run_pipeline(profile_name=profile)

            # Résumé toutes les 12 cycles (~1h si interval=300s)
            if cycle % 12 == 0:
                send_summary(get_stats())

            interval_min = settings.LOOP_INTERVAL // 60
            print(f"\n💤 Prochain cycle dans {interval_min} min...")
            await _interruptible_sleep(settings.LOOP_INTERVAL)
    finally:
        if bot_task:
            bot_task.cancel()


def cmd_missions():
    """Affiche les dernières missions."""
    missions = get_all_missions(20)
    if not missions:
        print("Aucune mission en base.")
        return
    for m in missions:
        score_pct = int((m.get("score") or 0) * 100)
        print(f"[{score_pct:3d}%] [{m['status']:8s}] {m['title'][:70]}")
        print(f"       {m['source']} → {m['url'][:80]}")
        print()


# =============================================================
# CLI
# =============================================================

def main():
    parser = argparse.ArgumentParser(
        description="🤖 Mission Agent — trouve tes missions freelance"
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("run", help="Lance une seule fois")
    subparsers.add_parser("loop", help="Tourne en boucle (daemon)")
    subparsers.add_parser("test", help="Teste la connexion Telegram")
    subparsers.add_parser("status", help="Affiche les stats")
    subparsers.add_parser("missions", help="Liste les dernières missions")

    # Commandes multi-profils
    profiles_p = subparsers.add_parser("profiles", help="Liste les profils disponibles")
    loop_p = subparsers.add_parser("loop-profile", help="Lance en boucle avec un profil")
    loop_p.add_argument("profile", choices=list_profiles(), help="Nom du profil")

    args = parser.parse_args()

    print_banner()

    # Initialise la DB toujours
    init_db()

    if args.command == "run" or args.command is None:
        asyncio.run(run_once())
        print_status()

    elif args.command == "loop":
        print("🚀 Démarrage en mode daemon...\n")
        ok = test_telegram()
        if ok:
            print("✅ Telegram opérationnel\n")
        else:
            print("⚠️  Telegram non configuré — vérifie TELEGRAM_TOKEN et TELEGRAM_CHAT_ID\n")
        asyncio.run(run_loop())

    elif args.command == "test":
        print("🧪 Test Telegram...")
        ok = test_telegram()
        if ok:
            print("✅ Message envoyé avec succès !")
        else:
            print("❌ Échec — vérifie ton TELEGRAM_TOKEN et TELEGRAM_CHAT_ID")

    elif args.command == "status":
        print_status()

    elif args.command == "missions":
        cmd_missions()

    elif args.command == "profiles":
        print("\n🎯 Profils disponibles :\n")
        for name in list_profiles():
            p = get_profile(name)
            src_info = f" ({len(p.sources_override)} sources)" if p.sources_override else ""
            print(f"  [{name}] {p.label}{src_info}")
            print(f"    Keywords: {', '.join(p.keywords[:4])}...")
            print(f"    Seuil: {p.min_score:.0%} | Budget min: {p.min_budget}€")
            print()

    elif args.command == "loop-profile":
        profile_name = args.profile
        print(f"🚀 Démarrage avec le profil [{profile_name}]...\n")
        ok = test_telegram()
        if ok:
            print("✅ Telegram opérationnel\n")
        asyncio.run(run_loop(profile=profile_name))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
