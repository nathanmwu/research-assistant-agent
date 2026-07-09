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


# --- source credibility (Phase 7) -----------------------------------------------

def test_source_kind_is_a_factual_label():
    k = tools.source_kind
    assert k("https://www.linkedin.com/pulse/foo") == "social"
    assert k("https://REDDIT.com/r/x") == "social"          # case-insensitive
    assert k("https://ies.ed.gov/paper") == "academic"
    assert k("https://web.mit.edu/x") == "academic"          # subdomain suffix match
    assert k("https://pmc.ncbi.nlm.nih.gov/articles/1") == "academic"
    assert k("https://doi.org/10.1000/x") == "academic"
    assert k("https://someblog.com/post") == "web"           # default bucket
    assert k("https://notlinkedin.com/x") == "web"           # suffix must not overmatch


class _CapturingClient:
    def __init__(self):
        self.kwargs = {}

    def search(self, query, **kwargs):
        self.kwargs = kwargs
        return {"results": []}


def test_search_excludes_ugc_at_the_api(monkeypatch):
    fake = _CapturingClient()
    monkeypatch.setattr(tools, "_client", fake)
    tools.tavily_search("any query")
    assert "linkedin.com" in fake.kwargs["exclude_domains"]
    assert "reddit.com" in fake.kwargs["exclude_domains"]


def test_cache_key_includes_the_exclusion_list(monkeypatch, tmp_path):
    # same query + different exclusions -> different results -> must not collide
    monkeypatch.setenv("CACHE", "1")
    monkeypatch.setattr(tools, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(tools, "_client", _CapturingClient())
    tools.tavily_search("same query")
    monkeypatch.setattr(tools, "UGC_DOMAINS", ("only.example",))
    tools.tavily_search("same query")
    assert len(list(tmp_path.glob("search-*.json"))) == 2
