"""Offline tests for the page-reading machinery — no browser, no network.

The seam: all of read_page's browser work happens in tools._fetch_rendered,
so tests fake exactly that one name and assert the policy around it.
"""
from agent import tools

ARTICLE = """<html><body><article><h1>Fraction pedagogy</h1>
<p>Number lines help students see fractions as numbers rather than pictures.
Research on middle school classrooms shows consistent gains when teachers
anchor instruction in measurement contexts and equivalence reasoning.</p>
<p>Manipulatives such as fraction strips support the transition from concrete
models to abstract procedures, especially for struggling learners who need
repeated concrete-to-abstract cycles before fluency develops.</p>
</article></body></html>"""


def test_read_page_extracts_clean_text(monkeypatch):
    monkeypatch.setattr(tools, "_fetch_rendered", lambda url: ARTICLE)
    text = tools.read_page("https://a.com/article")
    assert text and "Number lines" in text
    assert "<p>" not in text  # markup and boilerplate stripped


def test_read_page_returns_none_when_browser_fails(monkeypatch):
    def boom(url):
        raise TimeoutError("page hung past PAGE_TIMEOUT_S")
    monkeypatch.setattr(tools, "_fetch_rendered", boom)
    assert tools.read_page("https://slow.example.com/") is None  # degrade, never raise


def test_read_page_returns_none_for_non_html(monkeypatch):
    monkeypatch.setattr(tools, "_fetch_rendered", lambda url: None)
    assert tools.read_page("https://a.com/page") is None


def test_read_page_skips_binary_urls_without_launching(monkeypatch):
    def boom(url):
        raise AssertionError("browser must not launch for binary URLs")
    monkeypatch.setattr(tools, "_fetch_rendered", boom)
    assert tools.read_page("https://a.com/paper.PDF?utm_source=x") is None


def test_cache_replays_page_fetches(monkeypatch, tmp_path):
    monkeypatch.setenv("CACHE", "1")
    monkeypatch.setattr(tools, "_CACHE_DIR", tmp_path)
    calls = []
    monkeypatch.setattr(tools, "_fetch_rendered",
                        lambda url: calls.append(url) or ARTICLE)
    first = tools.read_page("https://a.com/x")
    second = tools.read_page("https://a.com/x")
    assert first == second and first is not None
    assert calls == ["https://a.com/x"]  # second call replayed from disk
