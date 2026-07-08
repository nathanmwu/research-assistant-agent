# Phase 5 report — Streamlit UI (2026-07-07)

**Outcome:** the agent has its face. `app.py` renders the identical dual stream the CLI consumes — live plan checklist, activity feed, token-streaming briefing, grounding verdicts — in ~150 lines. **33 tests green** (31 prior + 2 UI). Demo mode (`HEADLESS=0`) pops a visible Chromium window for every source read, so you can watch the agent browse next to the app.

## What was built

| Piece | Purpose |
|---|---|
| `main()` in `app.py` | One blocking loop over `graph.stream(..., stream_mode=["updates","messages"])` inside a single script run. Dispatch mirrors `cli.py` handler-for-handler: same node names, same state deltas — the graph is UI-agnostic by construction, so the UI is a thin renderer. |
| `_plan_markdown(subs, cursor)` | The plan as a live checklist: ✅ answered · ⚠️ thin · ⬜ pending · 🔄 the row under research. Pure function — the UI's only tested logic (`test_app.py`). |
| Briefing panel | `messages`-mode tokens (filtered to synthesize) accumulate into one `st.empty()` placeholder with a typing cursor; a gap round resets it under a "(revised)" header; after `verify`, the panel swaps to `final` — draft + Limitations. |
| Session pinning | Streamlit reruns the whole script on every interaction; the finished run is pinned into `st.session_state.last` and re-rendered statically, so the briefing survives any click. |
| UI run artifact | Per the transparency rule, every UI run writes `runs/ui-<slug>.log` (question, full event feed, final briefing). |
| `HEADLESS` knob | `config.HEADLESS` (env `HEADLESS`, default on) → `tools._fetch_rendered`. `HEADLESS=0` = demo/debug mode with visible browsers. Default stays headless so the repo remains server/CI-safe. |

## Incident: port 8501 already taken

The first demo launch failed — Nathan's own Streamlit instance was already serving on 8501 (Brave connected). Two lessons recorded:
1. Never assume the port; check `lsof` before concluding the app is "up" (a 200 from *someone else's* server fooled the first health check).
2. **Env is baked at server start:** Streamlit hot-reloads `app.py` per rerun, but imported modules (`agent.config`) stay cached in the process — a running server keeps the `HEADLESS` value it launched with. The demo instance went to :8502 with `HEADLESS=0` instead of touching Nathan's process.

## Honest limits
- The UI log records events and the final text, not per-token timing.
- The visual done-when (watching plan/searches/reads stream and browsers pop) is inherently a human check — performed live rather than asserted by pytest, per the testing strategy.
- Phase 6 (follow-up questions, README, graph PNG) is deferred by choice; `st.session_state` already holds what follow-ups would need.
