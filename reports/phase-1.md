# Phase 1 report — Walking skeleton (2026-07-06)

**Outcome:** end-to-end pipeline works. `python cli.py "…"` streams plan → per-sub-question searches/reads → token-streamed cited briefing. **9 offline tests, 0 API calls, 4.4s.** Full run log: [`runs/phase1-fractions.log`](../runs/phase1-fractions.log) (4 sub-questions, 4 searches, 8 sources, every `[S#]` resolvable).

**Discovery:** LangGraph forbids a node and a state key sharing a name → node is `plan`, state key is `sub_questions`.

## Files added

| File | Functions | Purpose |
|---|---|---|
| `agent/state.py` | `SubQuestion` / `Source` / `Finding` / `ResearchState`, `initial_state()`, `ResearchPlan` / `PageNotes` | The data contract. One shared state dict; nodes return partial updates that overwrite. Global, never-reused source ids keep `[S#]` stable forever. |
| `agent/tools.py` | `tavily_search()`, `_cached()` | The I/O seam tests monkeypatch. `raw_content` = Phase-1 "reading" + permanent scrape fallback. `CACHE=1` replays calls from `.cache/` (quota + reproducibility). Live smoke: `python -m agent.tools`. |
| `agent/nodes.py` | `plan()`, `search()`, `read()`, `advance()` (stub), `route_after_advance()`, `synthesize()` | `plan`: one structured call → capped, ordered checklist. `search`: zero LLM calls — sub-question text is the query; consumes `next_query`. `read`: dedupe by URL, register, compress-at-read (raw text never travels past this node). `advance`: stub brain, holds the invariant (cursor moves ⇒ attempts reset, next_query cleared). `synthesize`: plain `llm.invoke` from findings only, so tokens can stream. |
| `agent/graph.py` | `build_graph()` | Wiring only. Shape frozen from day one: `plan → (search → read → advance)* → synthesize`. |
| `cli.py` | `main()` | Dual-mode streaming: `updates` → timeline lines; `messages` filtered to the synthesize node → live briefing tokens. Sets `recursion_limit=100` ahead of Phase 2's loops. |
| `test_graph.py` | 9 tests | Routers, the invariant, query selection/consumption, read dedupe/numbering/cap/fallback/irrelevance, plan capping, graph shape. All seams faked with inline canned dicts. |

## Files changed
- `agent/config.py` — `RESULTS_PER_SEARCH = 5`.
- `requirements.txt` — `pytest`.

## Expected oddities (correct for this phase)
- Every search shows `#1` — the stub brain never retries (Phase 2's job).
- Sources can be read but uncited (S2/S6 in the log) — registration ≠ citation; only the reverse is checked.
