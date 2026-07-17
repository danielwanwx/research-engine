# Task Plan — Research Engine Maximum-Capability Audit

Goal: evidence-backed capability audit + prioritized backlog for the Research Engine. Audit-only.

## Phases
| # | Phase | Status |
|---|-------|--------|
| 0a | Baseline scaffolding (scope, manifest, git snapshot) | complete |
| 0b | Launch research_observer | complete (after 4x 529 retries; fresh spawn on sonnet, combined A+B contract) |
| 0c | Repo inventory, doctor, tests | complete |
| 1 | Benchmark plan before running | complete |
| 2 | Execute benchmarks B1-B8 | complete |
| 3 | Self-hosting + labeled external fallback | complete |
| 4 | Gap matrix (25 dims) | complete |
| 5 | Backlog (18 items) | complete |
| 6 | Reconciliation + final | in_progress (awaiting observer) |

## Key decisions
- Observer implemented as two-phase subagent (harness cannot stream live tool calls to a sibling): phase A captures baseline now; phase B (via SendMessage after observable trace is complete on disk) audits commands.jsonl + run dirs + artifacts and seals its report BEFORE reading any main-report conclusion files. Main agent does not read observer files until reconciliation.
- All main-agent commands logged to commands.jsonl (append-only) so the observer has a real observable trace.
- Engine runs go to runs/ (gitignored, pre-existing output dir — allowed as engine's own output path); audit copies/analyses live under audits/.

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|

| Observer 529 x4 | 1-4 | fresh spawn on sonnet model pool, combined contract; disclosed in decision_log |
| B1 run dir overwritten by B7 | 1 | engine behavior; documented as evidence, notes captured pre-overwrite |
