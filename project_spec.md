# Project Spec

## Purpose

An autonomous research assistant that turns a question worth 20–30 minutes of human research into a structured, cited briefing — showing its work live: the plan it made, each search it ran, each source it read, then the briefing itself streaming in. Follow-up questions trigger additional focused research rounds. Portfolio goals: learn multi-step agent planning and web-grounded generation; demonstrate both, legibly, to EdTech and mission-driven tech companies.

See [architecture.md](architecture.md) for the graph, state, and node design.

## Technology choices

| Technology | Why |
|---|---|
| **Python + LangGraph** | The explicit named-node graph is the point: plan → search → read → evaluate → synthesize → reflect → verify as readable, streamable control flow. No other LangChain machinery beyond what it pulls in. |
| **Gemini via `langchain-google-genai`** | **Native structured output** — every schema'd call is `with_structured_output(TypedDict)`, which deletes an entire pipeline step (no JSON-in-prompt, no parse-and-retry helper, no pydantic layer). Chosen over Gemma for exactly this reason. **Two-tier by design** (chosen 2026-07-07): plumbing calls (plan/read/evaluate/reflect) run on `gemini-3.1-flash-lite`, whose free quota covers a ~20–40-call run; `synthesize` — the 1–2 calls the reader actually sees — runs on premium `gemini-2.5-flash` (its 20 req/day still covers 10+ runs at that rate). Overrides: `GEMINI_MODEL` / `GEMINI_SMART_MODEL`. `agent/llm.py` is the single model seam and wraps every call in retry-on-5xx. Considered and deferred by choice: batched page compression, a client-side rate limiter, paid tier + parallel fan-out (the demo-day switch). |
| **Tavily** | Search API built for agents: clean ranked results, and `include_raw_content=True` returns extracted page text — the MVP's "reading" and the permanent fallback when scraping fails. |
| **Playwright** | Full-page reading for JS-rendered content. Used narrowly: render, hand off HTML. Headless Chromium, 15s hard timeout, no retries. |
| **trafilatura** | Rendered HTML → clean article text in one call. `BeautifulSoup.get_text()` returns nav/footer soup that would poison the grounding audit. |
| **Streamlit** | Single-file UI that can render the agent's stream live. |
| **python-dotenv** | Keys in gitignored `.env`; the repo is destined to be public. |

**Deliberately not used:** `create_react_agent`/prebuilt agents (the hand-wired graph *is* the demo) · Tavily's `include_answer` (it would do our synthesis for us — the technique being demonstrated) · LangSmith/Studio (the streamed UI is the observability) · checkpointers (session state covers follow-ups).

## Build plan

One phase ≈ one sitting; each ends as a reviewable, runnable piece with its "done when" check actually run.

### Phase 0 — Skeleton & the LLM seam ✅ (done 2026-07-03)
`agent/config.py` (dotenv, model id, caps) · `agent/llm.py` (Gemini client + `structured()`, smoke test in `__main__`) · `requirements.txt` · `.gitignore` · `.env.example`.
**Done when:** `python -m agent.llm` round-trips a structured output — TypedDict in, populated dict back. ✅ Passed.

### Phase 1 — Walking skeleton: real graph shape, dumb brain ✅ (done 2026-07-06)
`agent/state.py` · `agent/nodes.py` with `plan`, `search`, `read` (Tavily `raw_content` only), stub `advance` in place of evaluate (always "sufficient", pure cursor bump), `synthesize` · `agent/graph.py` with the cursor loop's conditional edge · `cli.py` streaming `stream_mode=["updates","messages"]` — timeline lines plus synthesize tokens live · the ~10-line disk cache for search (`CACHE=1`), which saves quota through every later phase · `test_graph.py` — first control-flow tests (cursor router, read dedupe/numbering); adds `pytest` to requirements.
**Done when:** `python cli.py "…"` streams plan → per-sub-question searches/reads → briefing typing itself out, end to end. *The graph shape is final from day one — Phase 2 upgrades a node, never restructures.* ✅ Passed: 9 offline tests green in 4.4s; live run on the fractions question streamed 4 sub-questions → 4 searches → 8 sources → token-streamed briefing, all citations resolvable.

### Phase 2 — Judgment: the loops become real ✅ (done 2026-07-06)
Replace `advance` with real `evaluate` (verdict + refined query + attempts cap + `thin` marking); add `reflect` + gap-append + re-synthesize; routers enforce caps. Extend `test_graph.py`: the three evaluate outcomes, the attempts cap, reflect's gap-append/cursor property.
**Done when:** an obscure question visibly triggers ≥1 refined search; caps hold (≤3 attempts/sub-question, ≤1 reflection round); a gap round appends questions and the briefing gains those sections; `pytest` green. ✅ Passed: the dyscalculia question triggered 6 refined searches (never a 4th attempt), 3 thin markings, one gap round (+2 sub-questions, revised briefing with both new sections), and a budget-stop that disclosed 2 open gaps; 18 offline tests green.

### Phase 3 — Real reading ✅ (done 2026-07-07)
`read_page()` in `agent/tools.py`: Playwright → trafilatura, fallback chain (→ `raw_content` → snippet), URL dedupe, non-HTML skip. `playwright install chromium` happens here. `test_tools.py` covers the fallback chain with a faked Playwright failure; `python -m agent.tools` becomes the live fetch smoke.
**Done when:** a JS-heavy page extracts clean text; a forced timeout degrades gracefully without killing the run; `pytest` green. ✅ Passed: `python -m agent.tools` extracted 1,071 clean chars from a JS-only page and returned None (no crash) on a forced timeout; live EdTech run read 10/10 sources via playwright (`runs/20260707-141613.log`); 25 offline tests green.

### Phase 4 — Grounding guardrail ☐ (next)
`verify` node: mechanical citation pass (regex) + one-call audit + inline `⚠` flags + Limitations assembly into `final`. Plus `test_verify.py`.
**Done when:** a test draft with (a) a fake citation id and (b) a fabricated claim gets both caught — (a) mechanically, (b) by the audit. This test must never break.

### Phase 5 — Streamlit UI ☐
`app.py`: live timeline (plan checklist, searches, sources), token-streamed briefing, results pinned in `st.session_state`.
**Done when:** a browser visitor watches the plan, searches, and reads appear live, and the briefing token-streams into place.

### Phase 6 — Follow-ups & portfolio polish ☐
Session source registry + follow-up planning mode (1–2 targeted sub-questions, citation numbering continues); README with auto-generated graph diagram (`graph.get_graph().draw_mermaid_png()`), demo GIF, one example briefing, export-to-markdown.
**Done when:** a follow-up reuses sources with continuous numbering; the README sells the project without a live demo.

## Complexity traps → pre-committed exits

| Trap | Exit |
|---|---|
| Scraping rabbit hole | 15s timeout, no retries, fallback chain, skip non-HTML, 8k char cap. Never a site-specific handler. |
| Unbounded loops / cost | Every loop: state counter + config cap; routers check caps first. Worst case ≈ 21 searches / ~25 LLM calls, known in advance. |
| Context blowup | Compress at read time; raw pages never travel past `read`. |
| Schema drift | Native structured output parses; keep schemas flat TypedDicts anyway. |
| Parallelism temptation | Sequential only — the streamed narrative is the product. |
| Streamlit rerun model | One blocking stream loop per run; pin results in `session_state`; no threads/async. |
| Free-tier quota burn | Phase-1 disk cache makes dev runs replayable (Tavily ~1000 credits/mo is plenty with it); two-tier models keep LLM quota inside free limits — premium flash only ever pays for synthesis. |
| Prompt sprawl | Prompts are f-string constants next to their node. No template engine, no prompt files. |

## Testing strategy

**Organizing principle: `pytest` = deterministic; `__main__` = live.** The default `pytest` run is offline, sub-second, costs zero API calls, and must always be green. Live checks against real services are `__main__` smoke blocks in the seam modules (`python -m agent.llm`, later `python -m agent.tools`), run deliberately when touching that seam — never as part of the suite.

Why this split: the system has two failure classes that need opposite treatment. **Control-flow bugs** (wrong route, `attempts` not resetting with `cursor`, a cap not holding) are deterministic and catastrophic — infinite loops, silently skipped sub-questions — and perfectly unit-testable, since routers are pure functions of state. **Judgment quality** (plan quality, verdict accuracy, briefing prose) is nondeterministic and not assertable — mocking an LLM to grade it only verifies the mocks. Judgment is evaluated by reading golden-run output, not by pytest.

### What gets automated tests, in build order

| Target | Why it matters | How |
|---|---|---|
| Routers + the cursor/attempts invariant | The control flow *is* the agent | Build a state dict, call the router/node, assert route + state update. LLM/search faked by monkeypatching `llm.structured` / `tools.tavily_search` with canned dicts written inline in the test. (Phase 1) |
| `read`'s URL dedupe + source-id numbering | Citation stability | Same pattern. (Phase 1) |
| `evaluate`'s three outcomes: answered / refine / exhausted→`thin` | The loop's brain stem | Canned verdicts in, assert cursor/attempts/`next_query`/status out. (Phase 2) |
| `reflect`'s gap-append + automatic cursor pickup | The zero-special-case property the design leans on | (Phase 2) |
| Fetch fallback chain: Playwright fails → `raw_content` → snippet; truncation; non-HTML skip | The anti-rabbit-hole policy must actually hold | Fake the Playwright call raising/timing out. (Phase 3) |
| `verify` mechanical layer: fake `[S#]` id, uncited paragraph | The deterministic half of the guardrail | Pure-function tests. (Phase 4) |
| `verify` audit catches a fabricated claim | The guardrail's reason to exist | The one live-LLM test; auto-skips when no API key is present. (Phase 4) |

Test files sit flat at repo root (`test_graph.py`, `test_tools.py`, `test_verify.py`) — pytest auto-discovers them. `pytest` joins `requirements.txt` in Phase 1.

### Test-shaped design rules (from Phase 1 onward)

- Nodes do I/O **only** through `tools.py` / `llm.py` — one monkeypatch point, no patching deep internals.
- Routers are named top-level functions, never lambdas — importable by tests.
- Fixtures are inline canned dicts in the test file. No recorded-cassette/VCR apparatus — the `CACHE=1` disk cache is a dev convenience for interactive runs, not a test fixture system.

### Deliberately untested

Prompt wording, briefing prose quality, Streamlit rendering (manual eyeball; `st.testing.AppTest` only if real UI logic ever accumulates), and live scraping of arbitrary sites inside pytest. No CI until the repo splits out of the monorepo — then one GitHub Action running the offline suite (Phase 6, optional).

## Verification

- **Per phase:** the "done when" checks above, actually run.
- **End to end:** the two canonical questions — "What are the most effective techniques for teaching fractions to middle schoolers?" and "How are EdTech companies using AI agents in their products right now?" A good run: plan streams first with rationales → at least one visible refined query → briefing with executive summary, one cited section per sub-question, numbered sources → Limitations section when coverage was thin → 2–5 minutes.
- **Guardrail regression:** `test_verify.py` always passes.
- **The demo test:** a full CLI event log, read top to bottom by a stranger, should tell a sensible research story — that log is the portfolio pitch.
