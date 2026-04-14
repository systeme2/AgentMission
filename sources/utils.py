# =============================================================
# sources/utils.py — helpers partagés pour les scrapers
# =============================================================

import asyncio
import requests


async def async_fetch(url: str, **kwargs) -> requests.Response:
    """
    Wrapper non-bloquant pour requests.get.

    Exécute requests.get dans un thread séparé via asyncio.to_thread,
    ce qui libère l'event loop asyncio pendant la requête HTTP.
    Sans ceci, les scrapers bloquent l'event loop et empêchent le bot
    Telegram de traiter les commandes (/pause, /interval, etc.)
    pendant le scraping.
    """
    return await asyncio.to_thread(requests.get, url, **kwargs)
