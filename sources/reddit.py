# =============================================================
# sources/reddit.py — scraper Reddit via API JSON publique
# =============================================================

import asyncio
import requests
from config.settings import settings

HEADERS = {
    "User-Agent": "MissionAgentBot/1.0 (personal freelance tracker)"
}

SUBREDDITS = [
    "forhire",
    "freelance",
    "learnprogramming",
    "webdev",
    "slavelabour",
]

# Mots-clés pour filtrer les posts "Hiring"
HIRING_TAGS = ["[hiring]", "[h]", "hiring:", "looking for", "we need", "job offer"]


async def get_reddit_jobs() -> list:
    print("🕷️  [Reddit] Scraping en cours...")
    jobs = []

    for sub in SUBREDDITS:
        try:
            url = f"https://www.reddit.com/r/{sub}/new.json?limit=25"
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            posts = data.get("data", {}).get("children", [])

            for post in posts:
                d = post.get("data", {})
                title = d.get("title", "")
                text = d.get("selftext", "")
                link = "https://www.reddit.com" + d.get("permalink", "")
                flair = (d.get("link_flair_text") or "").lower()

                # On garde seulement les posts "Hiring"
                is_hiring = (
                    any(tag in title.lower() for tag in HIRING_TAGS) or
                    flair in ["hiring", "job offer", "[hiring]"]
                )

                if not is_hiring:
                    continue

                jobs.append({
                    "title": title,
                    "description": text[:500],
                    "url": link,
                    "source": f"reddit/{sub}",
                    "budget_raw": "",
                })

            await asyncio.sleep(settings.REQUEST_DELAY)

        except Exception as e:
            print(f"  ⚠️  [Reddit/{sub}] Erreur: {e}")

    print(f"  ✅ [Reddit] {len(jobs)} missions trouvées")
    return jobs
