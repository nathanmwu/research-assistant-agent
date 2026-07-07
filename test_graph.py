"""Offline control-flow tests: no network, no API calls, sub-second.

Seam rule: nodes do I/O only via `nodes.tools.tavily_search`,
`nodes.structured`, and `nodes.llm` — so tests monkeypatch exactly those
names with canned data and assert the state updates.
"""
from agent import nodes
from agent.state import initial_state


class FakeStructured:
    """Stands in for structured(schema): .invoke returns a canned payload."""

    def __init__(self, payload):
        self.payload = payload

    def invoke(self, prompt):
        return self.payload


def state_with_plan(n=2, cursor=0):
    s = initial_state("test question")
    s["sub_questions"] = [
        {"id": i + 1, "question": f"sub {i + 1}", "rationale": "r", "status": "pending"}
        for i in range(n)
    ]
    s["cursor"] = cursor
    return s


RESULTS = [
    {"url": "https://a.com", "title": "A", "content": "snippet a", "raw_content": "full a"},
    {"url": "https://b.com", "title": "B", "content": "snippet b", "raw_content": ""},
    {"url": "https://c.com", "title": "C", "content": "snippet c", "raw_content": "full c"},
]


# --- routers -----------------------------------------------------------------

def test_router_loops_while_subquestions_remain():
    assert nodes.route_after_evaluate(state_with_plan(2, cursor=1)) == "search"


def test_router_exits_to_synthesize_when_plan_done():
    assert nodes.route_after_evaluate(state_with_plan(2, cursor=2)) == "synthesize"


def test_reflect_router_reenters_loop_after_gap_append():
    assert nodes.route_after_reflect(state_with_plan(4, cursor=2)) == "search"


def test_reflect_router_done_when_no_gaps_appended():
    assert nodes.route_after_reflect(state_with_plan(2, cursor=2)) == "done"


# --- evaluate (the loop's brain: three outcomes + the invariant) ---------------

SUFFICIENT = {"sufficient": True, "missing": "", "refined_query": ""}
INSUFFICIENT = {"sufficient": False, "missing": "no concrete data",
                "refined_query": "sharper query"}


def test_evaluate_sufficient_advances_and_resets_loop_state(monkeypatch):
    monkeypatch.setattr(nodes, "structured", lambda schema: FakeStructured(SUFFICIENT))
    s = state_with_plan(2, cursor=0)
    s["attempts"], s["next_query"] = 2, "stale refined query"
    out = nodes.evaluate(s)
    assert out["cursor"] == 1
    assert out["attempts"] == 0
    assert out["next_query"] is None
    assert out["sub_questions"][0]["status"] == "answered"
    assert s["sub_questions"][0]["status"] == "pending"  # input never mutated


def test_evaluate_insufficient_with_budget_refines_and_stays(monkeypatch):
    monkeypatch.setattr(nodes, "structured", lambda schema: FakeStructured(INSUFFICIENT))
    s = state_with_plan(2, cursor=0)
    s["attempts"] = 1  # < MAX_ATTEMPTS_PER_SUB_Q
    out = nodes.evaluate(s)
    assert out == {"next_query": "sharper query"}  # cursor untouched, no status change


def test_evaluate_exhausted_marks_thin_and_moves_on(monkeypatch):
    monkeypatch.setattr(nodes, "structured", lambda schema: FakeStructured(INSUFFICIENT))
    s = state_with_plan(2, cursor=0)
    s["attempts"] = 3  # == MAX_ATTEMPTS_PER_SUB_Q: budget spent
    out = nodes.evaluate(s)
    assert out["sub_questions"][0]["status"] == "thin"
    assert out["cursor"] == 1 and out["attempts"] == 0 and out["next_query"] is None


def test_evaluate_insufficient_without_query_goes_thin(monkeypatch):
    # defensive: model says insufficient but offers no refined query -> nothing
    # actionable, so treat the budget as spent rather than loop pointlessly
    verdict = {"sufficient": False, "missing": "x", "refined_query": ""}
    monkeypatch.setattr(nodes, "structured", lambda schema: FakeStructured(verdict))
    s = state_with_plan(2, cursor=0)
    s["attempts"] = 1
    out = nodes.evaluate(s)
    assert out["sub_questions"][0]["status"] == "thin"
    assert out["cursor"] == 1


# --- reflect (gap-append + budget + disclosure) --------------------------------

def answered_state(n=2):
    s = state_with_plan(n, cursor=n)
    for sq in s["sub_questions"]:
        sq["status"] = "answered"
    s["draft"] = "a draft briefing"
    return s


def test_reflect_appends_capped_gaps_and_cursor_picks_them_up(monkeypatch):
    gaps = [{"question": f"gap {i}", "rationale": "r"} for i in range(3)]
    monkeypatch.setattr(nodes, "structured",
                        lambda schema: FakeStructured({"answered": False, "gaps": gaps}))
    s = answered_state(2)
    out = nodes.reflect(s)
    subs = out["sub_questions"]
    assert len(subs) == 4                        # 3 gaps capped to MAX_GAP_QUESTIONS=2
    assert [sq["id"] for sq in subs[2:]] == [3, 4]  # ids continue, never reused
    assert all(sq["status"] == "pending" for sq in subs[2:])
    assert out["reflection_rounds"] == 1
    merged = {**s, **out}
    assert nodes.route_after_reflect(merged) == "search"  # cursor 2 < 4: loop re-enters


def test_reflect_budget_spent_discloses_open_gaps(monkeypatch):
    gaps = [{"question": "gap A", "rationale": "r"}]
    monkeypatch.setattr(nodes, "structured",
                        lambda schema: FakeStructured({"answered": False, "gaps": gaps}))
    s = answered_state(2)
    s["reflection_rounds"] = 1  # == MAX_REFLECTION_ROUNDS
    out = nodes.reflect(s)
    assert out == {"open_gaps": ["gap A"]}  # no append, no extra round
    assert nodes.route_after_reflect({**s, **out}) == "done"


def test_reflect_answered_is_done(monkeypatch):
    monkeypatch.setattr(nodes, "structured",
                        lambda schema: FakeStructured({"answered": True, "gaps": []}))
    out = nodes.reflect(answered_state(2))
    assert out == {"open_gaps": []}


# --- search -------------------------------------------------------------------

def test_search_uses_subquestion_verbatim_first(monkeypatch):
    seen = []
    monkeypatch.setattr(nodes.tools, "tavily_search",
                        lambda q: (seen.append(q), RESULTS[:1])[1])
    out = nodes.search(state_with_plan(cursor=0))
    assert seen == ["sub 1"]
    assert out["last_query"] == "sub 1"
    assert out["attempts"] == 1
    assert out["next_query"] is None


def test_search_consumes_pending_refined_query(monkeypatch):
    monkeypatch.setattr(nodes.tools, "tavily_search", lambda q: [])
    s = state_with_plan()
    s["next_query"], s["attempts"] = "refined query", 1
    out = nodes.search(s)
    assert out["last_query"] == "refined query"
    assert out["attempts"] == 2
    assert out["next_query"] is None  # consumed — can never leak forward


# --- read (dedupe, numbering, cap, relevance, transient results) ---------------

def test_read_dedupes_numbers_globally_and_caps(monkeypatch):
    monkeypatch.setattr(nodes.tools, "read_page", lambda url: None)  # force fallbacks
    monkeypatch.setattr(nodes, "structured",
                        lambda schema: FakeStructured({"relevant": True, "notes": "- fact [S2]"}))
    s = state_with_plan()
    s["sources"] = [{"id": 1, "url": "https://a.com", "title": "A",
                     "content": "old", "via": "tavily"}]
    s["results"] = RESULTS
    out = nodes.read(s)
    assert [src["url"] for src in out["sources"]] == [
        "https://a.com", "https://b.com", "https://c.com"]  # a deduped; b, c added (cap = 2)
    assert [src["id"] for src in out["sources"]] == [1, 2, 3]  # ids global + stable
    assert out["sources"][1]["content"] == "snippet b"  # no raw_content -> snippet
    assert [src["via"] for src in out["sources"][1:]] == ["snippet", "tavily"]
    assert len(out["findings"]) == 2
    assert out["results"] == []  # transient channel cleared


def test_read_prefers_rendered_page_over_fallbacks(monkeypatch):
    monkeypatch.setattr(nodes.tools, "read_page", lambda url: "rendered page text")
    monkeypatch.setattr(nodes, "structured",
                        lambda schema: FakeStructured({"relevant": True, "notes": "- x [S1]"}))
    s = state_with_plan()
    s["results"] = RESULTS[:1]
    out = nodes.read(s)
    assert out["sources"][0]["content"] == "rendered page text"
    assert out["sources"][0]["via"] == "playwright"


def test_read_drops_irrelevant_pages(monkeypatch):
    monkeypatch.setattr(nodes.tools, "read_page", lambda url: None)
    monkeypatch.setattr(nodes, "structured",
                        lambda schema: FakeStructured({"relevant": False, "notes": ""}))
    s = state_with_plan()
    s["results"] = RESULTS[:1]
    out = nodes.read(s)
    assert len(out["sources"]) == 1   # still registered (it was fetched)
    assert out["findings"] == []      # but contributes no evidence


# --- plan ----------------------------------------------------------------------

def test_plan_caps_size_and_initializes_statuses(monkeypatch):
    payload = {"sub_questions": [{"question": f"q{i}", "rationale": "r"} for i in range(8)]}
    monkeypatch.setattr(nodes, "structured", lambda schema: FakeStructured(payload))
    out = nodes.plan(initial_state("big question"))
    subs = out["sub_questions"]
    assert len(subs) == 5  # MAX_SUB_QUESTIONS
    assert [sq["id"] for sq in subs] == [1, 2, 3, 4, 5]
    assert all(sq["status"] == "pending" for sq in subs)


# --- text normalization ---------------------------------------------------------

def test_text_of_normalizes_all_content_shapes():
    from agent.llm import text_of
    assert text_of("plain string") == "plain string"
    parts = [
        {"type": "text", "text": "Hello, ", "index": 0},
        {"type": "text", "text": "world", "index": 0},
        {"type": "text", "text": "", "extras": {"signature": "abc"}, "index": 0},
    ]
    assert text_of(parts) == "Hello, world"


# --- run logging -----------------------------------------------------------------

def test_tee_mirrors_writes_to_all_streams():
    import io
    from cli import _Tee
    a, b = io.StringIO(), io.StringIO()
    tee = _Tee(a, b)
    tee.write("hello")
    tee.flush()
    assert a.getvalue() == b.getvalue() == "hello"


# --- graph shape ----------------------------------------------------------------

def test_graph_compiles_with_expected_nodes():
    from agent.graph import build_graph
    nodes_in_graph = set(build_graph().get_graph().nodes)
    assert {"plan", "search", "read", "evaluate", "synthesize", "reflect"} <= nodes_in_graph
