# =============================================================
# tests/phase3/conftest.py — fixtures pytest Phase 3
# =============================================================

import sys, os, json, xml.etree.ElementTree as ET
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tests.phase1.conftest import (
    make_html, make_json_jobs,
    assert_valid_job, assert_no_duplicates, assert_description_truncated,
    REQUIRED_FIELDS,
)


# ── Générateurs de données fictives ──────────────────────────

def make_algolia_response(hits: list[dict]) -> dict:
    """Simule la réponse JSON de l'API Algolia HackerNews."""
    return {
        "hits":           hits,
        "nbHits":         len(hits),
        "page":           0,
        "nbPages":        1,
        "hitsPerPage":    len(hits),
        "processingTimeMS": 1,
    }


def make_hn_thread_hit(object_id: str = "39894219", title: str = "Ask HN: Who is hiring? (March 2024)") -> dict:
    return {"objectID": object_id, "title": title, "created_at": "2024-03-01T10:00:00Z"}


def make_hn_comment_hit(
    object_id: str = "39894300",
    text: str = "Acme Corp | React Developer | Remote | Full-time | $120k\nWe are looking for a senior React developer...",
    story_id: str = "39894219",
) -> dict:
    return {
        "objectID":      object_id,
        "comment_text":  text,
        "story_id":      story_id,
        "created_at":    "2024-03-01T12:00:00Z",
    }


def make_devto_article(
    art_id: int = 1,
    title: str = "We're hiring a React Developer (Remote)",
    tag: str = "hiring",
) -> dict:
    return {
        "id":           art_id,
        "title":        title,
        "slug":         f"hiring-react-{art_id}",
        "description":  "We are looking for a senior React developer to join our team.",
        "url":          f"https://dev.to/company/hiring-react-{art_id}",
        "published_at": "2024-03-15T10:00:00Z",
        "user":         {"username": "company"},
        "tags": [{"name": tag}, {"name": "webdev"}],
    }


def make_twitter_api_response(tweets: list[dict]) -> dict:
    """Simule la réponse de l'API Twitter v2."""
    return {
        "data": tweets,
        "meta": {"newest_id": "1", "oldest_id": "0", "result_count": len(tweets)},
    }


def make_tweet(tweet_id: str = "1234567890", text: str = "We're hiring a remote React developer! #hiring #freelance") -> dict:
    return {
        "id":         tweet_id,
        "text":       text,
        "created_at": "2024-03-15T10:00:00Z",
    }


def make_nitter_rss(items: list[dict]) -> bytes:
    """Génère un flux RSS Nitter minimal valide."""
    channel = ET.Element("channel")
    for it in items:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text       = it.get("title", "Tweet test")
        ET.SubElement(item, "link").text         = it.get("link",  "https://twitter.com/i/web/status/123")
        ET.SubElement(item, "description").text  = it.get("description", "We are hiring a developer")
        ET.SubElement(item, "pubDate").text       = it.get("pubDate", "Mon, 15 Mar 2024 10:00:00 +0000")
    rss = ET.Element("rss", version="2.0")
    rss.append(channel)
    return ET.tostring(rss, encoding="unicode").encode()


def make_ih_nextdata(jobs: list[dict]) -> str:
    """Génère du HTML avec __NEXT_DATA__ contenant des jobs IndieHackers."""
    payload = {"props": {"pageProps": {"jobs": jobs}}}
    data    = json.dumps(payload)
    return f"""<!DOCTYPE html><html><body>
<script id="__NEXT_DATA__" type="application/json">{data}</script>
</body></html>"""


def make_mock_response(content, status: int = 200, content_type: str = "text/html"):
    from unittest.mock import MagicMock
    m = MagicMock()
    m.status_code = status
    m.url         = "https://example.com/page"
    m.headers     = {"Content-Type": content_type}
    if isinstance(content, bytes):
        m.content = content
        m.text    = content.decode("utf-8", errors="replace")
    elif isinstance(content, str):
        m.content = content.encode()
        m.text    = content
    else:
        import json as _j
        enc       = _j.dumps(content).encode()
        m.content = enc
        m.text    = enc.decode()
        m.json    = MagicMock(return_value=content)
    m.raise_for_status = MagicMock(
        side_effect=None if status < 400 else Exception(f"HTTP {status}")
    )
    return m
