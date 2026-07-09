"""Shared graph state + structured-output schemas.

LangGraph concept: the whole graph shares ONE state dict. Each node returns a
partial update containing only the keys it changed; LangGraph merges that in.
With no reducers configured, a returned key overwrites the previous value —
fine here because execution is strictly sequential.

Naming note: LangGraph forbids a node and a state key sharing a name, so the
node is called "plan" and the state key is `sub_questions`.
"""
from typing import TypedDict


class SubQuestion(TypedDict):
    id: int
    question: str
    rationale: str
    status: str    # pending | answered | thin
    evidence: str  # "academic" (scholarly backing warranted) | "general" — the planner's call


class Source(TypedDict):
    id: int       # cited as [S{id}]
    url: str
    title: str
    content: str  # cleaned page text, truncated to SOURCE_CHAR_LIMIT
    via: str      # "playwright" (rendered) | "tavily" (raw_content) | "snippet"
    kind: str     # "academic" | "web" — factual label from source_kind(); social is never registered


class Finding(TypedDict):
    sub_q_id: int
    notes: str  # markdown bullets with inline [S#] refs and short quotes


class ResearchState(TypedDict):
    question: str                   # the user's question — read by everything
    sub_questions: list[SubQuestion]  # the plan; reflect may append (Phase 2)
    cursor: int                     # index of the sub-question being researched
    attempts: int                   # search rounds spent on current sub-question
    last_query: str                 # what search just ran (drives the UI)
    next_query: str | None          # refinement from evaluate, consumed by search
    results: list[dict]             # this round's hits (transient; read clears it)
    sources: list[Source]           # global registry — cited as [S1], [S2], …
    findings: list[Finding]         # compressed evidence notes
    draft: str                      # briefing from synthesize
    reflection_rounds: int
    open_gaps: list[str]            # gaps reflect couldn't fill (budget spent) — disclosed in Limitations
    flagged: list[str]              # claims that failed the grounding audit (Phase 4)
    final: str                      # draft + flags + Limitations (Phase 4)
    history: list[dict]             # prior Q/briefing pairs, for follow-ups (Phase 6)


def initial_state(question: str) -> ResearchState:
    return ResearchState(
        question=question, sub_questions=[], cursor=0, attempts=0,
        last_query="", next_query=None, results=[], sources=[], findings=[],
        draft="", reflection_rounds=0, open_gaps=[], flagged=[], final="",
        history=[],
    )


# --- structured-output schemas (what Gemini must return, per call) ---------


class PlannedSubQuestion(TypedDict):
    question: str
    rationale: str
    evidence: str  # "academic" | "general"


class ResearchPlan(TypedDict):
    sub_questions: list[PlannedSubQuestion]


class PageNotes(TypedDict):
    relevant: bool  # false when the page doesn't address the sub-question
    notes: str      # markdown bullets, each ending with its [S#] marker


class Evaluation(TypedDict):
    sufficient: bool
    missing: str        # what's absent ("" when sufficient)
    refined_query: str  # sharper search query targeting the gap ("" when sufficient)


class Reflection(TypedDict):
    answered: bool
    gaps: list[PlannedSubQuestion]  # material gaps only; may be empty


class ClaimAudit(TypedDict):
    claim: str      # brief quote of the problem claim from the draft
    source_id: int  # the [S#] the draft cites for it
    verdict: str    # "partial" | "unsupported"


class GroundingAudit(TypedDict):
    audits: list[ClaimAudit]  # ONLY claims that are not fully supported
