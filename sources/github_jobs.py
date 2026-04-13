# =============================================================
# sources/github_jobs.py — GitHub Jobs via GraphQL + discussions
# =============================================================
#
# GitHub n'a pas d'API Jobs officielle depuis 2021, mais deux
# sources alternatives sont très actives :
#
# 1. GitHub Discussions "Who is Hiring" dans des repos dédiés
#    ex: https://github.com/regonn/who-is-hiring (mensuel)
#
# 2. Topics GitHub: "jobs", "hiring", "freelance"
#    Repos taggés avec ces topics contenant des offres
#
# 3. GitHub Search API — issues/discussions avec "hiring"
#    GET https://api.github.com/search/issues
#    ?q=hiring+developer+remote+is:open+label:hiring
#
# Token optionnel (GITHUB_TOKEN) pour un rate limit plus élevé :
#   Sans token : 60 req/h
#   Avec token : 5000 req/h
# =============================================================

import asyncio
import os
import re
import requests
from config.settings import settings

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
BASE_URL     = "https://api.github.com"
HEADERS      = {
    "Accept":     "application/vnd.github.v3+json",
    "User-Agent": "MissionAgentBot/1.0",
}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"token {GITHUB_TOKEN}"

# Requêtes de recherche d'issues/discussions "hiring"
_SEARCH_QUERIES = [
    "hiring developer freelance remote is:open label:hiring",
    "looking for developer freelance remote is:open",
    "mission développeur freelance is:open",
]

# Repos connus pour publier des offres régulièrement
_KNOWN_JOB_REPOS = [
    "remoteintech/remote-jobs",
    "tramcar/tramcar",
]


def _is_relevant_issue(issue: dict) -> bool:
    """Filtre les issues qui semblent être des offres d'emploi."""
    title = (issue.get("title") or "").lower()
    body  = (issue.get("body") or "").lower()
    text  = title + " " + body

    hiring_kw = ["hiring", "looking for", "we need", "developer wanted",
                 "freelance", "remote", "mission", "développeur", "job"]
    negative  = ["bug", "feature request", "question", "help wanted",
                 "documentation", "duplicate", "invalid"]

    if any(neg in title for neg in negative):
        return False
    return any(kw in text for kw in hiring_kw)


def _parse_issue(issue: dict, source_label: str = "github.jobs") -> dict | None:
    """Convertit une issue GitHub en job dict."""
    title = (issue.get("title") or "").strip()
    if not title or len(title) < 5:
        return None

    url   = issue.get("html_url") or issue.get("url", "")
    body  = (issue.get("body") or "").strip()[:500]
    # Nettoyage markdown basique
    body  = re.sub(r"#+\s*", "", body)
    body  = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", body)
    body  = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", body)
    body  = body.strip()[:500]

    repo  = (issue.get("repository_url") or "").replace("https://api.github.com/repos/", "")
    if repo:
        title = f"{title} ({repo.split('/')[-1]})"

    return {
        "title":       title,
        "description": body,
        "url":         url,
        "budget_raw":  "",
        "source":      source_label,
    }


def _search_issues(query: str) -> list:
    """Recherche dans les issues GitHub."""
    jobs = []
    try:
        resp = requests.get(
            f"{BASE_URL}/search/issues",
            params={"q": query, "sort": "updated", "order": "desc", "per_page": 15},
            headers=HEADERS,
            timeout=15,
        )
        if resp.status_code == 403:
            print("  ⚠️  [GitHub Jobs] Rate limit atteint — ajoute GITHUB_TOKEN")
            return []
        resp.raise_for_status()
        items = resp.json().get("items", [])
        for item in items:
            if not _is_relevant_issue(item):
                continue
            job = _parse_issue(item)
            if job:
                jobs.append(job)
    except requests.RequestException as exc:
        print(f"  ⚠️  [GitHub Jobs] search '{query[:40]}': {exc}")
    return jobs


def _get_repo_issues(repo: str) -> list:
    """Récupère les issues ouvertes d'un repo de jobs connu."""
    jobs = []
    try:
        resp = requests.get(
            f"{BASE_URL}/repos/{repo}/issues",
            params={"state": "open", "per_page": 20, "sort": "updated"},
            headers=HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        # L'API peut retourner une liste directe OU un dict avec "items"
        items = data if isinstance(data, list) else data.get("items", [])
        for item in items:
            if not isinstance(item, dict):
                continue
            job = _parse_issue(item, "github.jobs")
            if job:
                jobs.append(job)
    except requests.RequestException as exc:
        print(f"  ⚠️  [GitHub Jobs] repo '{repo}': {exc}")
    return jobs


async def get_github_jobs() -> list:
    print("🕷️  [GitHub Jobs] Scraping en cours...")

    all_jobs:  list = []
    seen_urls: set  = set()

    # Recherche dans les issues
    for query in _SEARCH_QUERIES:
        batch = await asyncio.to_thread(_search_issues, query)
        for job in batch:
            if job["url"] not in seen_urls:
                seen_urls.add(job["url"])
                all_jobs.append(job)
        await asyncio.sleep(settings.REQUEST_DELAY)

    # Repos dédiés
    for repo in _KNOWN_JOB_REPOS:
        batch = await asyncio.to_thread(_get_repo_issues, repo)
        for job in batch:
            if job["url"] not in seen_urls:
                seen_urls.add(job["url"])
                all_jobs.append(job)
        await asyncio.sleep(settings.REQUEST_DELAY)

    print(f"  ✅ [GitHub Jobs] {len(all_jobs)} missions trouvées")
    return all_jobs
