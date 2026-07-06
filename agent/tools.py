"""External I/O lives here — the one seam tests monkeypatch.

Dev cache: run with CACHE=1 and every call is replayed from .cache/ on repeat,
saving Tavily quota and making dev runs reproducible while building downstream
nodes. Off by default so real runs stay real.
"""
import hashlib
import json
import os
from pathlib import Path

from tavily import TavilyClient

from agent.config import RESULTS_PER_SEARCH

_CACHE_DIR = Path(".cache")
_client = None  # lazy: importing this module must not require an API key


def _cached(kind: str, key: str, fetch):
    # ponytail: naive json-file cache, dev only; no eviction, delete .cache/ to reset
    if os.getenv("CACHE") != "1":
        return fetch()
    path = _CACHE_DIR / f"{kind}-{hashlib.sha256(key.encode()).hexdigest()[:16]}.json"
    if path.exists():
        return json.loads(path.read_text())
    out = fetch()
    _CACHE_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(out))
    return out


def tavily_search(query: str) -> list[dict]:
    """Top web results as [{url, title, content, raw_content}, ...].

    `content` is Tavily's snippet; `raw_content` is its extraction of the full
    page text — Phase 1's "reading", and the permanent fallback once Playwright
    lands in Phase 3.
    """
    def fetch():
        global _client
        if _client is None:
            _client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
        resp = _client.search(query, max_results=RESULTS_PER_SEARCH, include_raw_content=True)
        return [
            {
                "url": r["url"],
                "title": r["title"],
                "content": r["content"],
                "raw_content": r.get("raw_content") or "",
            }
            for r in resp["results"]
        ]

    return _cached("search", query, fetch)


if __name__ == "__main__":  # live smoke: python -m agent.tools
    hits = tavily_search("LangGraph streaming modes")
    assert hits and all(h["url"] and h["title"] for h in hits), hits
    got_raw = sum(1 for h in hits if h["raw_content"])
    print(f"smoke ok: {len(hits)} results ({got_raw} with raw_content); "
          f"first: {hits[0]['title']} ({hits[0]['url']})")
