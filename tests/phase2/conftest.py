# =============================================================
# tests/phase2/conftest.py — fixtures pytest Phase 2
# =============================================================

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import xml.etree.ElementTree as ET

# Re-exporte les helpers Phase 1 pour ne pas les dupliquer
from tests.phase1.conftest import (
    make_html, make_json_jobs,
    assert_valid_job, assert_no_duplicates, assert_description_truncated,
    REQUIRED_FIELDS,
)


# ── Générateurs de données fictives ──────────────────────────

def make_rss(items: list[dict]) -> bytes:
    """
    Génère un flux RSS minimal valide (bytes).
    Chaque dict peut avoir : title, link, description, pubDate, budget.
    """
    channel = ET.Element("channel")
    for it in items:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text       = it.get("title", "Test job")
        ET.SubElement(item, "link").text         = it.get("link", "https://example.com/job/1")
        ET.SubElement(item, "description").text  = it.get("description", "Job description")
        ET.SubElement(item, "pubDate").text       = it.get("pubDate", "Mon, 01 Jan 2024 00:00:00 +0000")

    rss  = ET.Element("rss", version="2.0")
    rss.append(channel)
    return ET.tostring(rss, encoding="unicode").encode()


def make_remoteok_json(n: int = 3) -> list:
    """
    Génère la réponse JSON typique de l'API Remote OK.
    Le premier élément est toujours le header légal.
    """
    header = {"legal": "Remote OK legal notice"}
    jobs   = [
        {
            "id":          str(i),
            "slug":        f"react-developer-{i}",
            "position":    f"React Developer #{i}",
            "company":     f"Company {i}",
            "description": f"<p>Description du poste {i}</p>",
            "tags":        ["react", "javascript", "remote"],
            "salary_min":  5000 * i,
            "salary_max":  7000 * i,
            "url":         f"https://remoteok.com/remote-jobs/react-developer-{i}",
            "date":        "2024-03-15T10:00:00Z",
        }
        for i in range(1, n + 1)
    ]
    return [header] + jobs


def make_freelancer_api_response(n: int = 3) -> dict:
    """Génère une réponse typique de l'API Freelancer.com."""
    projects = [
        {
            "id":    i,
            "title": f"WordPress site #{i}",
            "description": f"Build a WordPress website #{i}",
            "seo_url": f"wordpress-site-{i}",
            "budget": {"minimum": 200 * i, "maximum": 400 * i},
            "currency": {"sign": "$"},
            "language": "en",
        }
        for i in range(1, n + 1)
    ]
    return {"result": {"projects": projects}, "status": "success"}


def make_mock_response(content, status=200, content_type="text/html"):
    """Crée un mock de requests.Response."""
    from unittest.mock import MagicMock
    import json as json_lib

    m = MagicMock()
    m.status_code = status
    m.headers     = {"Content-Type": content_type}

    if isinstance(content, bytes):
        m.content = content
        m.text    = content.decode("utf-8", errors="replace")
    elif isinstance(content, str):
        m.content = content.encode()
        m.text    = content
    else:
        encoded   = json_lib.dumps(content).encode()
        m.content = encoded
        m.text    = encoded.decode()
        m.json    = MagicMock(return_value=content)

    m.raise_for_status = MagicMock(
        side_effect=None if status < 400 else Exception(f"HTTP {status}")
    )
    return m
