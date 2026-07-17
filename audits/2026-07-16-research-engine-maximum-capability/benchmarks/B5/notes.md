# B5 — GitHub ecosystem survey (open-source deep research agents)

- Command: `... run "open source deep research agent framework" --pack auto --depth audit --platform-scope all --source-timeout-seconds 30` (0.9s)
- Run dir: `runs/2026-07-16-open-source-deep-research-agent-framework`
- Result: complete, 12 github rows (audit depth cap 12). Note: without --web-search-pages the run is github-only — sensible.

## Findings
- Query normalization stripped "open source"/"repo" (github_public.py:71-75) → effective query "deep research agent framework"; that part works.
- **Ranking failure dominates**: `sort=updated` returns repos pushed this week. 6/12 have ≤2 stars; the field's canonical projects (assafelovic/gpt-researcher, stanford-oval/storm, langchain-ai open deep research, smolagents…) are ALL absent. A maintenance-weighted or best-match ranking would have surfaced them.
- **Schema gaps confirmed** (row keys): metrics = stars/forks/open_issues/language only. **No license, no releases, no contributors, no commit cadence, no archived flag.** The audit prompt's own rule 8 (evaluate maintenance/license, not stars) is unsatisfiable from engine output.
- updated_at/published_at present for github rows (the only connector with dates).
- Marginally relevant: awesome-ai-agents-2026 (list), heurist-agent-framework, LiteResearcher, DR-Arena. On-target for "leading frameworks": none.

## Rubric
Task understanding 3 · Source discovery 2 (autonomous but wrong ranking) · Primary ratio 3 (repos are primary artifacts) · Freshness 4 (dates present, recent by construction) · Relevant yield 1 · Diversity 1 (single API) · Extraction 3 (structured metrics) · Dup 3 · Conflict unavailable · Claim-citation 2 · Citation validity 4 (URLs valid) · Artifacts 5 · Failure transparency 3 · Self-repair 0 · Reproducibility 3 (sort=updated is time-sensitive; same command tomorrow returns different repos) · Latency 5 · Cost unavailable · Fallback n/a.

Headline per plan rubric: **1/5** (mostly irrelevant repos; no license/release/maintenance data).
