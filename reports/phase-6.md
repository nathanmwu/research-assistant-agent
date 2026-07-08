# Phase 6 report — Portfolio polish (2026-07-07)

**Outcome:** the project is finished. All output is professional monochrome, the stream reads as chapters, and the repo has its front door: a README with the auto-generated graph image and a real run excerpt. **34 tests green.** Final verification run: [`runs/phase6-edtech.log`](../runs/phase6-edtech.log) — new format end-to-end, with the guardrail catching three real over-claims plus one uncited passage into a populated Limitations section.

**Rescope, by choice:** the original Phase 6 included follow-up questions; Nathan dropped them. The session-state foundation for follow-ups remains in `app.py` if ever revisited.

## Changes

| Where | What | Why |
|---|---|---|
| `cli.py` + `app.py` | Emojis → ASCII + capitalized action labels ("Planned 4 sub-questions:", "Search #3:", "Sub-question 2/4 answered", "Reflection:", "Grounding:"); plan markers `[x]`/`[>]`/`[!]`; flags `!` | Emojis read as unprofessional AI artifacts; logs are now pure-ASCII grep-friendly text. |
| `cli.py` + `app.py` | Run-wide search counter for display | The old number was the per-sub-question `attempts` value (loop bookkeeping that resets on every cursor advance) — a smooth run displayed as all "Search #1", which read as a bug. State is unchanged; the narrative counter lives in the display layer, where narrative belongs. |
| `cli.py` + `app.py` | Divider after each resolved sub-question | The stream now reads as chapters: plan, then one delimited block per sub-question, then the briefing. |
| `agent/nodes.py` | Briefing flags: `⚠` → `[unverified]`; Limitations bullets → `- Flagged: …` | The guardrail's marks are part of the deliverable text — they survive copy-paste into any document now. |
| Headless | Demo server stopped; default was already headless | The visible-browser demo underwhelmed (windows open and close in ~2s). `HEADLESS=0` remains available for debugging. |
| `cli.py` `_Tee` | Survives `BrokenPipeError` per stream | See incident below. |
| `README.md` + `assets/graph.png` | Portfolio front door; PNG auto-generated from the compiled graph (`draw_mermaid_png()`, regen command in the README) | The diagram is generated from the code, so it can't drift from reality. The README's example run deliberately shows a *flagged* Limitations section — the guardrail visibly working is the credibility feature. |

## Incident: `| head -40` killed a live run

The first verification run was piped through `head -40` for display. `head` exits after 40 lines, the pipe closes, and the CLI's next `print` raised `BrokenPipeError` mid-briefing — run dead, log truncated, quota spent. Fix at the choke point every write routes through: `_Tee` now drops a dead stream and keeps writing to the survivors, so a dying console pipe can never kill a run or its log again (regression: `test_tee_survives_a_dead_console_pipe`). The rerun used the correct pattern — redirect console output, read the log.

## Final project numbers

- 7 graph nodes, 2 routers, 3 capped loops; worst case ~21 searches / ~25 LLM calls, known before running
- 34 tests: 33 deterministic + 1 live guardrail regression
- 6 phases, each with a report in `reports/` and named run logs in `runs/`
- ~15 source files; `nodes.py` still reads top-to-bottom
