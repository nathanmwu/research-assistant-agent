# Phase 3 report — Real reading (2026-07-07)

**Outcome:** sources are now read as rendered pages, not search extractions. **25 offline tests green.** Live evidence:
- `python -m agent.tools` (live smoke): extracted **1,071 clean chars from a JS-only page** (quotes.toscrape.com/js/ — its HTML is empty until JavaScript runs), and a forced timeout on an unroutable port returned `None` instead of crashing.
- Full run on *"How are EdTech companies using AI agents in their products right now?"* — 4 sub-questions, 1 refined search, **10/10 sources read `· playwright`**, reflection satisfied, all 10 citations resolvable, clean token streaming. Log: [`runs/phase3-edtech.log`](../runs/phase3-edtech.log).

Honest note: the live run never needed the fallback rungs (every page rendered). The rungs are proven deterministically instead — offline tests fake `_fetch_rendered` failing, and the smoke forces a real timeout. That's by design: correctness guarantees shouldn't depend on which pages the web happens to serve today.

## Functions added / changed

| Where | What | Purpose |
|---|---|---|
| `agent/tools.py` | `_fetch_rendered(url)` | Headless-Chromium render → HTML. Fresh browser per call (~1s overhead, zero lifecycle bugs). Real UA. Non-HTML content-type → None (Tavily's raw_content handles PDFs better than a browser screenshot of one). |
| `agent/tools.py` | `read_page(url)` | The policy wrapper: binary-extension pre-filter (never launches a browser for `.pdf` etc.) → render → `trafilatura.extract` (boilerplate-stripped article text — `get_text()` soup would poison findings and the Phase-4 audit) → `None` on any failure, **no retries** ("a page that resists for 15s doesn't make the briefing"). Cached under `CACHE=1`, failures included — dev replays stay deterministic; delete `.cache/` to reset. |
| `agent/nodes.py` | `read()` fallback chain | Best text first: rendered page (`via="playwright"`) → Tavily `raw_content` (`via="tavily"`) → snippet (`via="snippet"`). Never raises — each rung just degrades evidence quality one step, and the `via` label makes the degradation visible in every log line. |
| `cli.py` | read line shows `· via` | Transparency: you can see per-source which rung produced the text. |
| `test_tools.py` (new) | 5 tests | Clean extraction, browser-failure → None, non-HTML → None, binary URLs never launch a browser, cache replays fetches. All fake the single seam `tools._fetch_rendered`. |
| `test_graph.py` | read tests updated +1 | Rendered-page preference (`via="playwright"`), fallback `via` labels asserted. |

## Also in this phase window
- **Two-tier models** (decided 2026-07-07, before Phase 3 started): plumbing on `gemini-3.1-flash-lite`, synthesize on `gemini-2.5-flash` (`smart_llm`). Verified live on both tiers; batching/rate-limiter/paid-tier deferred by choice. Details in project_spec.md's stack table.
- `playwright install chromium` completed — the one-time setup step is now a README-line-1 item for anyone cloning.

## Setup note
New machine checklist grew by one: `pip install -r requirements.txt` **and** `python -m playwright install chromium`.
