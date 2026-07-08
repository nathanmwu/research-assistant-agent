# Phase 4 report — Grounding guardrail (2026-07-07)

**Outcome:** the graph is complete — all seven nodes live. Every claim in the final briefing is now checked against the evidence, and every shortfall (unsupported claims, thin coverage, unfilled gaps) lands in a visible **Limitations** section. **31 tests green**, including the suite's one live-LLM regression: the audit caught a fabricated "73% improvement" claim against the real model. Full run log: [`runs/phase4-dyscalculia.log`](../runs/phase4-dyscalculia.log).

## The run, concretely

The dyscalculia question again (deliberately evidence-poor). Everything fired at once:
- 20 sources; the fallback chain visible live for the first time — S15 `· tavily` (a PDF), S16 `· snippet` — alongside 18 rendered reads.
- Refinements, two `thin` markings, a gap round (+2 sub-questions), a revised briefing, budget-spent disclosure of 2 open gaps.
- **The audit flagged a real problem:** the draft quoted [S17] as saying Socratic questioning can be "embarrassing" and "do more harm than helping" — verdict **partial** (the finding supports a weaker version). Marked ⚠ inline, listed in Limitations.

## Functions added / changed

| Where | What | Purpose |
|---|---|---|
| `agent/nodes.py` | `_citation_issues(draft, valid_ids)` | **Layer 1, mechanical (regex, free, deterministic):** every `[S#]` must resolve to a registered source; every substantial line (≥100 chars, outside headings/source list) must carry a citation. No model can talk its way past it. |
| `agent/nodes.py` | `VERIFY_PROMPT` + `verify(state)` | **Layer 2, audit (1 LLM call):** each cited claim checked against the quote-bearing findings; verdicts `partial`/`unsupported` only ("empty list is the ideal outcome" — an honest exit, same trick as reflect's). Failures: ⚠ marked inline (best-effort exact-match), then assembled with thin sub-questions and `open_gaps` into `## Limitations`, appended to `final`. **Flag, never fix** — no verify→search loop; re-research at the last mile reopens unbounded work, disclosure closes it. |
| `agent/nodes.py` | `_findings_block(state)` | One formatter for the evidence: synthesize writes *from* it, verify audits *against* it — identical text both times, by construction. |
| `agent/nodes.py` | `route_after_reflect` → `"verify"` | The Phase-2 placeholder route (`"done"` → END) remapped; verify → END. |
| `agent/state.py` | `ClaimAudit`, `GroundingAudit` | Audit output schemas. |
| `cli.py` | verify handler + Limitations print | 🛡 line with each ⚠ flag, then the Limitations section itself — the log now contains the complete final deliverable. |
| `cli.py` | `RUN_LABEL` naming | Logs follow Nathan's `phaseN-topic.log` convention: `RUN_LABEL=…` wins, else a slug of the question; collisions get a time suffix instead of clobbering. |
| `test_verify.py` (new) | 6 tests | Mechanical layer: fake id flagged, long uncited passage flagged, headings/short-lines/source-list exempt. Node: flags + Limitations assembly, clean-draft-appends-nothing. **Live regression** (the one live test, auto-skips without a key): the real model must catch the fabricated claim. |

## Honest caveats
- The audit is judgment, not proof — it catches fabrication *reliably enough to demo*, not provably. The mechanical layer and quote-bearing findings do the structural work; the audit is the net under the net. (Already in architecture.md §4.)
- The uncited-passage rule is a ≥100-char heuristic: short uncited claims slip through; long meta-sentences ("evidence here is thin") can false-positive into Limitations — which errs on the disclosing side, the right side.
- Inline ⚠ marking requires the audit's quote to appear verbatim in the draft; when paraphrased, the flag still lands in Limitations, just not inline.

Next: Phase 5 — the Streamlit UI over the identical stream the CLI consumes.
