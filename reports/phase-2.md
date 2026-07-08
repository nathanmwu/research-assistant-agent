# Phase 2 report — Judgment loops (2026-07-06)

**Outcome:** the agent now judges its own evidence. All done-when behaviors demonstrated in one live run — **6 refined searches (never a 4th attempt), 3 `thin` markings, one gap round (+2 sub-questions, revised briefing with both new sections), and a budget-stop that disclosed 2 unresolved gaps.** 18 offline tests green. Full run log: [`runs/phase2-dyscalculia.log`](../runs/phase2-dyscalculia.log).

## The run, concretely

Question: *"How effective are AI-based Socratic tutoring systems for teaching fraction division to students with dyscalculia?"*

Planner produced 4 sub-questions:
1. Core characteristics of dyscalculia + challenges in fraction division
2. The Socratic tutoring method and how AI software implements it
3. Empirical research on AI Socratic tutoring effectiveness for dyscalculia
4. Design features/adaptations proven effective for dyscalculia

Outcomes: #1 answered after 1 refinement · #2 answered first try · #3 **thin** after 2 refinements (the evidence genuinely runs out — the briefing says so) · #4 answered. Reflection then found the draft under-answered the *original* question and appended:

5. Efficacy specifically for **fraction division** (vs. general math) → thin after 2 refinements
6. Limitations/negative impacts of Socratic questioning for dyscalculia → thin after 2 refinements

Second reflection: budget spent → 2 remaining gaps disclosed (see end of log), not silently dropped. 26 sources read.

Note: the briefing in this log prints as raw `{'type': 'text', ...}` fragments — that's the content-parts bug being discovered (fixed the same day, see incidents below). Later runs stream clean text.

## Functions added / replaced

| Where | What | Purpose |
|---|---|---|
| `agent/nodes.py` | `evaluate()` (replaces stub `advance`) | Judge + refine in one structured call: `{sufficient, missing, refined_query}`. Exits: answered → advance · insufficient w/ budget → store `next_query`, stay · exhausted (or no usable query) → `thin`, advance. Holds the cursor/attempts invariant. |
| `agent/nodes.py` | `route_after_evaluate()` | Same pure cursor check as Phase 1's router — retry vs. next-sub-question both return `"search"`; state encodes which. |
| `agent/nodes.py` | `reflect()` | Acceptance-test of the **draft against the original question** (never sees sources). Exits: answered → done · gaps + budget → append as `pending` sub-questions (ids continue), bump `reflection_rounds` · gaps, no budget → `open_gaps` for Limitations. Zero special-case routing: the cursor, parked at the end of the old plan, points at gap #1 automatically. |
| `agent/nodes.py` | `route_after_reflect()` | `"search"` if the cursor is valid again, else `"done"` (Phase 4 remaps to `verify`). |
| `agent/state.py` | `Evaluation`, `Reflection`, `open_gaps` field | Output schemas + the disclosure channel (distinct from Phase 4's `flagged`). |
| `agent/llm.py` | retry wrapper, `text_of()` | Incident-driven, see below. |
| `agent/graph.py` | rewire | `evaluate` in; `synthesize → reflect`; reflect's conditional edge. |
| `cli.py` | evaluate/reflect handlers, `_Tee` | 🔁 refine, ⚠️ thin, 🪞 all three reflect outcomes, "briefing (revised)". `_Tee` mirrors every run (incl. tracebacks) to a timestamped `runs/*.log`. |
| `test_graph.py` | +10 tests (19 total) | Three evaluate outcomes + defensive fourth, both reflect routers, gap-append (cap, id continuity, cursor pickup), budget disclosure, `text_of` shapes, `_Tee`. |

## Incidents (all live failures, all fixed at the llm seam)

1. **Gemini 503 mid-run** killed a 2-minute run → all model calls now wrapped in `.with_retry` (3 attempts, exponential jitter), **5xx only** — 4xx means the request is wrong (bad schema/key/quota) and won't heal by waiting.
2. **429: free tier of `gemini-2.5-flash` = 20 requests/day** on this key; one run needs ~20–40. Probed the key's model list live, verified structured output on lite tiers → dev default is now `gemini-3.1-flash-lite`, overridable per run via `GEMINI_MODEL=…`.
3. **Newer Gemini streams content as part-dicts, not strings** → briefing printed raw `{'type': 'text', ...}`. Fixed with `text_of()` in `llm.py`; `synthesize` and the CLI both use it.

Three incidents, zero changes to any node — the single-model-seam design paying rent.
