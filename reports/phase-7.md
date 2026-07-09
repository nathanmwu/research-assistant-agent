# Phase 7 report — Question-aware source credibility (2026-07-08)

**Outcome:** the agent no longer trusts Tavily's ranking blindly, and it will never cite a LinkedIn post again. Credibility preference is **question-aware** — the planner decides, per sub-question, whether scholarly evidence is warranted — at **zero additional LLM calls**. **43 tests green.** Logs: [`runs/phase7-fractions.log`](../runs/phase7-fractions.log), [`runs/phase7-edtech.log`](../runs/phase7-edtech.log).

## Why this design

The trigger: a LinkedIn post cited as [S1] in a research briefing. The obvious fixes were both rejected — a fixed domain-tier policy ("academic always wins") misfires on landscape questions where vendor blogs and news ARE the right sources, and per-round LLM triage costs 4–8 calls per run. Nathan's steer: *the preference depends on the question.* So the judgment rides the planner's existing call, domain lists are demoted from policy to factual labeling, and social is banned outright.

## The three mechanics

1. **Social/UGC ban** — `UGC_DOMAINS` (config) enforced twice: Tavily's `exclude_domains` keeps it out of results; `read()` hard-skips any straggler. If only UGC evidence exists, the sub-question goes `thin` and is disclosed — the registry never holds a social source.
2. **Planner-owned preference** — `SubQuestion.evidence: "academic" | "general"`, judged during the existing plan call (reflect's gap questions get the same treatment). Downstream: `read()` stable-sorts academic-first *only* under academic preference (Tavily relevance stays the tiebreaker); `evaluate` sees the preference plus the kinds of sources consulted, so refined queries steer scholarly when the preference is unmet; `verify` adds a mechanical Limitations line when an academic-preferring sub-question ended up with only general web sources.
3. **Factual labeling** — `source_kind(url)` → academic / social / web, a pure suffix-match over config lists. It states facts ("this is a journal", "this is a social network"); the *preference* between facts is the planner's call. The label flows to read lines (`[academic]`), the briefing's Sources section, and the disclosure check.

## Functions added / changed

| Where | What |
|---|---|
| `agent/config.py` | `UGC_DOMAINS`, `ACADEMIC_DOMAINS` |
| `agent/tools.py` | `source_kind(url)`; `tavily_search` passes `exclude_domains`; **cache key now includes the exclusion list** (same query + different exclusions = different results; also prevents stale pre-change caches from resurrecting the LinkedIn result) |
| `agent/state.py` | `evidence` on `PlannedSubQuestion`/`SubQuestion`; `kind` on `Source` |
| `agent/nodes.py` | `_norm_evidence()` (model free-text → two values); plan + reflect prompts/constructors emit evidence; `read()` candidate filter + conditional academic-first sort; `EVALUATE_PROMPT` preference + sources-consulted context + scholarly-steering rule; synthesize source list carries kind; `verify()` unmet-preference disclosure |
| `cli.py` / `app.py` | `[academic]` marks on plan and read lines |
| `tests/` | +9: classifier facts (subdomains, case, no overmatch), API exclusion, cache-key variation, social-never-read, academic-first-only-when-asked, Tavily-order-under-general, evidence normalization/default, disclosure fires/doesn't |

## Live evidence

**Run A (fractions — empirical question):** planner marked 3/4 sub-questions `[academic]`; reads went to IES, Sage journals, PMC, a `.edu` repository, ScienceDirect (the phase-1 run on this same question had used blogs). Sub-question 1's preference couldn't be met → the disclosure fired: *"Scholarly evidence was preferred… but only general web sources were found."*

**Run B (EdTech landscape):** the two landscape sub-questions stayed `general` and drew industry/news sources in relevance order — correct for the question; the two empirical ones (pedagogical efficacy, ethics) went `[academic]` and drew ScienceDirect, Springer ×2, EDUCAUSE. **UGC grep across the log: 0.**

## Honest ceiling (documented add-back)

The classifier labels domains, not content: run B tagged CMU/UCSC *course-marketing* pages `[academic]` (they're `.edu`, not peer-reviewed), and a job-board page slipped through on the general track as relevance noise. That's the known coarseness of factual domain lists — the documented next step, if it matters in practice, is the per-round LLM triage call this phase deliberately declined.
