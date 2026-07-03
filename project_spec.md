# Project Spec

## Purpose

An autonomous research assistant that turns a question worth 20–30 minutes of human research into a structured, cited briefing — showing its work live: the plan it made, each search it ran, each source it read, then the briefing itself streaming in. Follow-up questions trigger additional focused research rounds. Portfolio goals: learn multi-step agent planning and web-grounded generation; demonstrate both, legibly, to EdTech and mission-driven tech companies.

See [architecture.md](architecture.md) for the graph, state, and node design.

## Technology choices

| Technology | Why |
|---|---|
| **Python + LangGraph** | The explicit named-node graph is the point: plan → search → read → evaluate → synthesize → reflect → verify as readable, streamable control flow. No other LangChain machinery beyond what it pulls in. |
| **Gemini (`gemini-2.5-flash`) via `langchain-google-genai`** | Fast, cheap, generous free tier, and **native structured output** — every schema'd call is `with_structured_output(TypedDict)`, which deletes an entire pipeline step (no JSON-in-prompt, no parse-and-retry helper, no pydantic layer). Chosen over Gemma for exactly this reason. Model id is one config string; `agent/llm.py` is the single model seam. |
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

### Phase 1 — Walking skeleton: real graph shape, dumb brain ☐ (next)
`agent/state.py` · `agent/nodes.py` with `plan`, `search`, `read` (Tavily `raw_content` only), stub `advance` in place of evaluate (always "sufficient", pure cursor bump), `synthesize` · `agent/graph.py` with the cursor loop's conditional edge · `cli.py` streaming `stream_mode=["updates","messages"]` — timeline lines plus synthesize tokens live · the ~10-line disk cache for search (`CACHE=1`), which saves quota through every later phase.
**Done when:** `python cli.py "…"` streams plan → per-sub-question searches/reads → briefing typing itself out, end to end. *The graph shape is final from day one — Phase 2 upgrades a node, never restructures.*

### Phase 2 — Judgment: the loops become real ☐
Replace `advance` with real `evaluate` (verdict + refined query + attempts cap + `thin` marking); add `reflect` + gap-append + re-synthesize; routers enforce caps.
**Done when:** an obscure question visibly triggers ≥1 refined search; caps hold (≤3 attempts/sub-question, ≤1 reflection round); a gap round appends questions and the briefing gains those sections.

### Phase 3 — Real reading ☐
`read_page()` in `agent/tools.py`: Playwright → trafilatura, fallback chain (→ `raw_content` → snippet), URL dedupe, non-HTML skip. `playwright install chromium` happens here.
**Done when:** a JS-heavy page extracts clean text; a forced timeout degrades gracefully without killing the run.

### Phase 4 — Grounding guardrail ☐
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
| Free-tier quota burn | Phase-1 disk cache makes dev runs replayable; Tavily's ~1000 credits/mo is plenty with it. |
| Prompt sprawl | Prompts are f-string constants next to their node. No template engine, no prompt files. |

## Verification

- **Per phase:** the "done when" checks above, actually run.
- **End to end:** the two canonical questions — "What are the most effective techniques for teaching fractions to middle schoolers?" and "How are EdTech companies using AI agents in their products right now?" A good run: plan streams first with rationales → at least one visible refined query → briefing with executive summary, one cited section per sub-question, numbered sources → Limitations section when coverage was thin → 2–5 minutes.
- **Guardrail regression:** `test_verify.py` always passes.
- **The demo test:** a full CLI event log, read top to bottom by a stranger, should tell a sensible research story — that log is the portfolio pitch.
