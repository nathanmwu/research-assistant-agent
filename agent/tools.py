"""External I/O lives here — the one seam tests monkeypatch.

Dev cache: run with CACHE=1 and every call is replayed from .cache/ on repeat,
saving Tavily quota and making dev runs reproducible while building downstream
nodes. Off by default so real runs stay real.
"""
import hashlib
import json
import os
from pathlib import Path

import trafilatura
from tavily import TavilyClient

from agent.config import HEADLESS, PAGE_TIMEOUT_S, RESULTS_PER_SEARCH

_CACHE_DIR = Path(".cache")
_client = None  # lazy: importing this module must not require an API key

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
_BINARY_EXTENSIONS = (".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".zip")


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


def _fetch_rendered(url: str) -> str | None:
    """Rendered HTML via headless Chromium, or None for non-HTML responses.

    Fresh browser per call: ~1s overhead, zero lifecycle bugs. Singleton only
    if that second ever actually hurts.
    """
    from playwright.sync_api import sync_playwright  # heavy import: only when scraping

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        try:
            page = browser.new_page(user_agent=_UA)
            resp = page.goto(url, timeout=PAGE_TIMEOUT_S * 1000)
            if resp is not None and "text/html" not in resp.headers.get("content-type", ""):
                return None  # PDFs etc. — Tavily's raw_content handles those better
            return page.content()
        finally:
            browser.close()


def read_page(url: str) -> str | None:
    """Full page text — rendered by Playwright, boilerplate-stripped by
    trafilatura — or None when the page resists (timeout, non-HTML, nothing
    extractable).

    No retries, by policy: a page that resists for PAGE_TIMEOUT_S seconds
    doesn't make the briefing. The read node falls back to Tavily's
    raw_content, then the search snippet.
    """
    if url.lower().split("?")[0].endswith(_BINARY_EXTENSIONS):
        return None  # don't even launch a browser for binary content

    def fetch():
        try:
            html = _fetch_rendered(url)
        except Exception:  # timeout, DNS, TLS, browser crash — all the same answer
            return None
        return trafilatura.extract(html) if html else None

    return _cached("page", url, fetch)


if __name__ == "__main__":  # live smoke: python -m agent.tools
    hits = tavily_search("LangGraph streaming modes")
    assert hits and all(h["url"] and h["title"] for h in hits), hits
    got_raw = sum(1 for h in hits if h["raw_content"])
    print(f"search ok: {len(hits)} results ({got_raw} with raw_content)")

    js_text = read_page("https://quotes.toscrape.com/js/")  # content exists only after JS runs
    assert js_text and "Einstein" in js_text, repr((js_text or "")[:200])
    print(f"js-render ok: {len(js_text)} chars, e.g. {js_text[:70]!r}")

    dead = read_page("https://example.com:81/")  # unroutable port → timeout → None
    assert dead is None
    print("timeout-degrade ok: returned None instead of raising")
