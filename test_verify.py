"""The guardrail regression — the one file that must never break.

The mechanical layer is tested offline like everything else. The audit-layer
test at the bottom is the suite's single live-LLM exception (documented in
project_spec's testing strategy): "the guardrail catches a fabricated claim"
is the most important behavior in the repo, so it runs against the real
model — and auto-skips when no API key is configured.
"""
import os

import pytest

from agent import nodes
from agent.state import GroundingAudit
from test_graph import FakeStructured, state_with_plan

# --- layer 1: mechanical citation checks (offline, deterministic) --------------


def test_unknown_citation_id_is_flagged():
    issues = nodes._citation_issues("Real fact [S1]. Fake fact [S9].", {1, 2})
    assert any("[S9]" in i for i in issues)
    assert not any("[S1]" in i for i in issues)


def test_long_uncited_passage_is_flagged():
    line = ("Manipulatives such as fraction strips measurably improve outcomes "
            "for struggling middle schoolers across dozens of classroom trials.")
    assert len(line) >= 100
    issues = nodes._citation_issues(line, set())
    assert any("uncited passage" in i for i in issues)


def test_headings_short_lines_and_source_list_are_exempt():
    heading = ("## A heading long enough that it would trip the uncited-passage "
               "filter if headings were not exempt from the citation rule")
    sources_line = ("A very long source-list line without any citation marker in it "
                    "at all, well past the hundred character threshold for flagging.")
    assert len(heading) >= 100 and len(sources_line) >= 100
    draft = (f"{heading}\n"
             "Short transition.\n"
             "A properly cited factual statement about fraction pedagogy and its "
             "effects on classroom outcomes [S1].\n"
             "## Sources\n"
             f"{sources_line}\n")
    assert nodes._citation_issues(draft, {1}) == []


# --- the verify node (offline, audit faked) -------------------------------------


def test_verify_assembles_flags_and_limitations(monkeypatch):
    audit = {"audits": [{"claim": "a 73% improvement", "source_id": 1,
                         "verdict": "unsupported"}]}
    monkeypatch.setattr(nodes, "structured", lambda schema: FakeStructured(audit))
    s = state_with_plan(2, cursor=2)
    s["sub_questions"][1]["status"] = "thin"
    s["open_gaps"] = ["an unanswered gap question"]
    s["sources"] = [{"id": 1, "url": "u", "title": "t", "content": "c", "via": "tavily"}]
    s["draft"] = "The study found a 73% improvement [S1]. Bogus cite [S7]."
    out = nodes.verify(s)

    assert any("[S7]" in f for f in out["flagged"])              # mechanical layer
    assert any("73% improvement" in f for f in out["flagged"])   # audit layer
    assert "a 73% improvement ⚠" in out["final"]                 # inline mark landed
    assert "## Limitations" in out["final"]
    assert "Evidence ran thin on: sub 2" in out["final"]
    assert "Not covered (research budget spent): an unanswered gap question" in out["final"]


def test_verify_clean_draft_appends_nothing(monkeypatch):
    monkeypatch.setattr(nodes, "structured",
                        lambda schema: FakeStructured({"audits": []}))
    s = state_with_plan(2, cursor=2)
    for sq in s["sub_questions"]:
        sq["status"] = "answered"
    s["sources"] = [{"id": 1, "url": "u", "title": "t", "content": "c", "via": "tavily"}]
    s["draft"] = "A tidy, well-cited claim [S1]."
    out = nodes.verify(s)
    assert out["flagged"] == []
    assert out["final"] == s["draft"]  # no Limitations section when nothing to disclose


# --- layer 2: the live regression (the one live-LLM test in the suite) ----------

requires_key = pytest.mark.skipif(
    not os.environ.get("GOOGLE_API_KEY"),
    reason="live grounding audit needs GOOGLE_API_KEY",
)


@requires_key
def test_live_audit_catches_fabricated_claim():
    findings = ("(sub-question 1)\n"
                "- Number lines help students see fractions as numbers rather than pictures [S1]\n"
                '- "Fraction strips support the move from concrete models to abstract procedures" [S1]')
    draft = ("Number lines help students compare fractions [S1]. "
             "A randomized controlled trial found a 73% test-score improvement "
             "after two weeks of number line practice [S1].")
    out = nodes.structured(GroundingAudit).invoke(
        nodes.VERIFY_PROMPT.format(draft=draft, findings=findings))
    assert any("73" in a["claim"] and a["verdict"] in ("unsupported", "partial")
               for a in out["audits"]), out
