"""Graph nodes: plan, search, read, evaluate, synthesize, reflect.
Phase 4 adds verify. The graph shape has been final since Phase 1.

LangGraph concepts:
- A node is a plain function: state in -> partial update dict out. Only the
  returned keys change; everything else carries forward.
- Routers (route_after_*) are pure functions of state returning the next
  node's name. They must never mutate state — any other return is discarded.

Seam rule (project_spec.md): all I/O goes through `tools.tavily_search`,
`structured`, or `llm`, so tests monkeypatch exactly those three names.
"""
from agent import tools
from agent.config import (
    MAX_ATTEMPTS_PER_SUB_Q, MAX_GAP_QUESTIONS, MAX_REFLECTION_ROUNDS,
    MAX_SUB_QUESTIONS, READS_PER_SUB_Q, SOURCE_CHAR_LIMIT,
)
from agent.llm import llm, structured, text_of
from agent.state import (
    Evaluation, Finding, PageNotes, Reflection, ResearchPlan, ResearchState,
    Source, SubQuestion,
)

PLAN_PROMPT = """\
You are planning web research to answer a question.

Break the question into the FEWEST sub-questions (3-{max_subs}) that would let
a competent generalist write a complete briefing. Rules:
- Each sub-question must be independently answerable by a web search — it must
  not depend on another sub-question's answer.
- Order foundation-first: definitions and landscape before specifics,
  comparisons, and evidence.
- rationale: one sentence on why the main question cannot be answered
  without this sub-question.

Question: {question}"""


def plan(state: ResearchState) -> dict:
    """Decompose the question into an ordered, capped checklist."""
    out = structured(ResearchPlan).invoke(
        PLAN_PROMPT.format(max_subs=MAX_SUB_QUESTIONS, question=state["question"])
    )
    return {
        "sub_questions": [
            SubQuestion(id=i + 1, question=sq["question"],
                        rationale=sq["rationale"], status="pending")
            for i, sq in enumerate(out["sub_questions"][:MAX_SUB_QUESTIONS])
        ]
    }


def search(state: ResearchState) -> dict:
    """Run one Tavily search for the current sub-question.

    Query choice: a refined query from evaluate if one is pending, else the
    sub-question text verbatim (the planner writes them to be searchable, so
    first attempts cost no LLM call). Consumes next_query either way so a
    stale refinement can never leak into a later round.
    """
    query = state["next_query"] or state["sub_questions"][state["cursor"]]["question"]
    return {
        "results": tools.tavily_search(query),
        "last_query": query,
        "attempts": state["attempts"] + 1,
        "next_query": None,
    }


NOTES_PROMPT = """\
You are reading one web page to help answer one research sub-question.

Sub-question: {sub_question}

Extract ONLY findings relevant to the sub-question, as 2-6 markdown bullets.
Every bullet must end with the citation marker [S{source_id}]. Where a short
verbatim quote carries the key evidence, include it in "quotes".
If the page does not address the sub-question at all, set relevant=false.

Page: {title} ({url})
---
{content}"""


def read(state: ResearchState) -> dict:
    """Read the top unseen results and compress each into a Finding.

    Compress-at-read is the load-bearing decision: downstream nodes only ever
    see these bounded, quote-bearing notes — raw page text never leaves this
    node. Dedupe is by URL against the global source registry; ids are
    assigned once, globally, so [S#] citations stay stable forever.
    """
    sub_q = state["sub_questions"][state["cursor"]]
    known = {s["url"] for s in state["sources"]}
    sources = list(state["sources"])
    findings = list(state["findings"])
    added = 0

    for r in state["results"]:
        if added >= READS_PER_SUB_Q:
            break
        if r["url"] in known:
            continue
        known.add(r["url"])
        added += 1
        text = (r["raw_content"] or r["content"])[:SOURCE_CHAR_LIMIT]
        src = Source(id=len(sources) + 1, url=r["url"], title=r["title"],
                     content=text, via="tavily")
        sources.append(src)
        notes = structured(PageNotes).invoke(NOTES_PROMPT.format(
            sub_question=sub_q["question"], source_id=src["id"],
            title=src["title"], url=src["url"], content=src["content"],
        ))
        if notes["relevant"]:
            findings.append(Finding(sub_q_id=sub_q["id"], notes=notes["notes"]))

    return {"sources": sources, "findings": findings, "results": []}


EVALUATE_PROMPT = """\
You are judging whether research on one sub-question is sufficient to write
its section of a briefing.

Sub-question: {sub_question}

Evidence gathered so far:
{findings}

The search that produced this evidence: "{last_query}"

Decide:
- sufficient=true when the evidence lets a writer answer the sub-question
  concretely. Enough beats perfect — do not demand exhaustiveness.
- If insufficient: state in one sentence what is missing, and give
  refined_query — a sharper web search targeting exactly that gap. Use
  different terms than the previous search; never repeat it verbatim.
- If sufficient, leave missing and refined_query as empty strings."""


def evaluate(state: ResearchState) -> dict:
    """Judge and refine in one call — the loop's brain.

    Three exits:
    - sufficient            -> mark answered, advance cursor
    - insufficient, budget  -> store next_query, stay on this sub-question
    - insufficient, spent   -> mark thin, advance anyway (weak coverage becomes
                               visible output, never an infinite loop)

    The invariant lives here: whoever moves the cursor resets attempts and
    clears next_query.
    """
    sq = state["sub_questions"][state["cursor"]]
    notes = "\n\n".join(f["notes"] for f in state["findings"]
                        if f["sub_q_id"] == sq["id"]) or "None yet."
    out = structured(Evaluation).invoke(EVALUATE_PROMPT.format(
        sub_question=sq["question"], findings=notes, last_query=state["last_query"]))

    can_retry = state["attempts"] < MAX_ATTEMPTS_PER_SUB_Q and out["refined_query"]
    if not out["sufficient"] and can_retry:
        return {"next_query": out["refined_query"]}

    subs = [dict(s) for s in state["sub_questions"]]
    subs[state["cursor"]]["status"] = "answered" if out["sufficient"] else "thin"
    return {"sub_questions": subs, "cursor": state["cursor"] + 1,
            "attempts": 0, "next_query": None}


def route_after_evaluate(state: ResearchState) -> str:
    """Loop while sub-questions remain; synthesize when the cursor runs off
    the plan. Covers both search flavors — retry (cursor unchanged) and next
    sub-question — because state, not the route, encodes which."""
    return "search" if state["cursor"] < len(state["sub_questions"]) else "synthesize"


SYNTHESIZE_PROMPT = """\
Write a research briefing that answers: {question}

Structure (markdown):
1. `## Executive summary` — 3-5 sentences that directly answer the question.
2. One `##` section per sub-question below, in order, synthesizing its findings.
3. `## Sources` — the numbered source list exactly as given.

Rules:
- Every factual claim carries an inline citation marker like [S2], drawn ONLY
  from the findings below. Never invent a marker.
- If the findings for a sub-question are weak or missing, say so plainly
  instead of filling the gap from memory.

Sub-questions:
{sub_questions}

Findings — your only evidence; cite by the [S#] markers they contain:
{findings}

Sources on record:
{source_list}"""


def synthesize(state: ResearchState) -> dict:
    """Write the briefing from findings only — never raw sources.

    Plain llm.invoke (not structured): free-form markdown, and it lets
    stream_mode="messages" surface the tokens live.
    """
    subs = "\n".join(f"{sq['id']}. {sq['question']}  [{sq['status']}]"
                     for sq in state["sub_questions"])
    notes = "\n\n".join(f"(sub-question {f['sub_q_id']})\n{f['notes']}"
                        for f in state["findings"])
    srcs = "\n".join(f"[S{s['id']}] {s['title']} — {s['url']}"
                     for s in state["sources"])
    msg = llm.invoke(SYNTHESIZE_PROMPT.format(
        question=state["question"], sub_questions=subs,
        findings=notes, source_list=srcs,
    ))
    text = text_of(msg.content)
    # final == draft until verify (Phase 4) starts appending flags/limitations
    return {"draft": text, "final": text}


REFLECT_PROMPT = """\
You are reviewing a research briefing before delivery.

Original question: {question}

Sub-questions researched (with status):
{sub_questions}

Draft briefing:
{draft}

Judge strictly by outcome:
- answered=true when a reasonable reader who asked the ORIGINAL question would
  consider it answered by this draft. Covering adjacent sub-topics is not the
  test; the original question is.
- Report only gaps MATERIAL to the original question — things the reader must
  know that the draft does not tell them. Nice-to-have additions are not gaps.
  Reporting zero gaps is a perfectly good outcome.
- Each gap must be a NEW sub-question, independently answerable by a web
  search — not a rewrite request. At most {max_gaps}."""


def reflect(state: ResearchState) -> dict:
    """Acceptance-test the draft against the original question.

    Judges the deliverable, not the research trail — so its inputs are the
    question, the plan statuses, and the draft. Never the sources.

    Three exits:
    - answered (or no usable gaps) -> done
    - gaps + budget left  -> append them as pending sub-questions; the cursor,
      already parked at len(sub_questions), now points at the first gap and
      the ordinary search loop runs the fill round — zero special cases
    - gaps + budget spent -> record them in open_gaps for the Limitations
      section; disclosed, never silently dropped
    """
    subs_txt = "\n".join(f"{sq['id']}. {sq['question']}  [{sq['status']}]"
                         for sq in state["sub_questions"])
    out = structured(Reflection).invoke(REFLECT_PROMPT.format(
        question=state["question"], sub_questions=subs_txt,
        draft=state["draft"], max_gaps=MAX_GAP_QUESTIONS))

    gaps = out["gaps"][:MAX_GAP_QUESTIONS]
    if out["answered"] or not gaps:
        return {"open_gaps": []}
    if state["reflection_rounds"] >= MAX_REFLECTION_ROUNDS:
        return {"open_gaps": [g["question"] for g in gaps]}

    start = len(state["sub_questions"])
    appended = state["sub_questions"] + [
        SubQuestion(id=start + i + 1, question=g["question"],
                    rationale=g["rationale"], status="pending")
        for i, g in enumerate(gaps)
    ]
    return {"sub_questions": appended,
            "reflection_rounds": state["reflection_rounds"] + 1}


def route_after_reflect(state: ResearchState) -> str:
    """Gap questions appended -> back into the research loop; otherwise done.
    (Phase 4 remaps "done" to the verify node.)"""
    return "search" if state["cursor"] < len(state["sub_questions"]) else "done"
