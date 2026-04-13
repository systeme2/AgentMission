# =============================================================
# tests/phase1/conftest.py — fixtures pytest partagées
# =============================================================

import pytest
import sys
import os

# Rendre le projet importable depuis n'importe où
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ── Constantes de validation ─────────────────────────────────

REQUIRED_FIELDS = {"title", "description", "url", "budget_raw", "source"}


# ── HTML fictifs pour mocker les réponses réseau ─────────────

def make_html(cards: list[dict], card_class="mission-card") -> str:
    """
    Génère un HTML minimal contenant des fausses cartes de missions.
    Chaque dict peut avoir : title, url, description, budget.
    """
    items = []
    for c in cards:
        href   = c.get("url", "https://example.com/job/1")
        title  = c.get("title", "Développeur WordPress freelance")
        desc   = c.get("description", "Description de la mission")
        budget = c.get("budget", "500 €")
        items.append(f"""
        <article class="{card_class}">
            <h2><a href="{href}">{title}</a></h2>
            <p class="description">{desc}</p>
            <span class="budget">{budget}</span>
        </article>""")

    return f"""<!DOCTYPE html>
<html><body>
    {''.join(items)}
</body></html>"""


def make_json_jobs(n: int = 3, source_prefix: str = "test") -> list:
    """Génère une liste de faux jobs au format attendu par l'agent."""
    return [
        {
            "title":       f"Mission {source_prefix} {i}",
            "description": f"Description {i}",
            "url":         f"https://example.com/{source_prefix}/job/{i}",
            "budget_raw":  f"{(i + 1) * 200} €",
            "source":      source_prefix,
        }
        for i in range(1, n + 1)
    ]


# ── Validateurs réutilisables ────────────────────────────────

def assert_valid_job(job: dict, source_name: str | None = None):
    """Vérifie qu'un job respecte le contrat attendu par l'agent."""
    for field in REQUIRED_FIELDS:
        assert field in job, f"Champ manquant '{field}' dans le job: {job}"

    assert isinstance(job["title"], str),       "title doit être str"
    assert isinstance(job["description"], str), "description doit être str"
    assert isinstance(job["url"], str),         "url doit être str"
    assert isinstance(job["budget_raw"], str),  "budget_raw doit être str"
    assert isinstance(job["source"], str),      "source doit être str"

    assert len(job["title"]) > 0, "title ne peut pas être vide"
    assert job["url"].startswith("http"), f"url invalide: {job['url']}"
    assert len(job["url"]) > 10,         f"url trop courte: {job['url']}"

    if source_name:
        assert job["source"] == source_name, (
            f"source attendu '{source_name}', obtenu '{job['source']}'"
        )


def assert_no_duplicates(jobs: list):
    urls = [j["url"] for j in jobs]
    assert len(urls) == len(set(urls)), (
        f"Doublons détectés: {len(urls) - len(set(urls))} URL(s) en double"
    )


def assert_description_truncated(jobs: list, max_len: int = 500):
    for job in jobs:
        assert len(job["description"]) <= max_len, (
            f"Description trop longue ({len(job['description'])} > {max_len}): "
            f"{job['title']}"
        )
