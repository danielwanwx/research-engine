# 02 — Benchmark Scoring Rubric

Every benchmark is scored 0–5 on each dimension below, from run artifacts only. If a dimension
cannot be measured from observable artifacts, score is `unavailable` (never guessed).
Per-benchmark success rubrics in 02_benchmark_plan.json take precedence for the headline verdict.

| Dimension | 0 | 3 | 5 |
|---|---|---|---|
| Task Understanding / Query Decomposition | topic ignored/misrouted | pack routed sensibly, queries generic | queries decomposed per facet and actually executed |
| Source Discovery | no sources | seeds/flags only, nothing autonomous | autonomous discovery of relevant new sources |
| Primary Source Ratio | 0% primary | mixed, majority secondary | majority official/primary for the question |
| Freshness Compliance | stale evidence presented as current | mixed ages, dates recorded but unchecked | all inside window or staleness explicitly flagged |
| Relevant Evidence Yield | 0 relevant rows | ~half relevant | >80% relevant to the question |
| Independent Domain Diversity | 1 domain | 2–3 domains, related | >=4 independent domains |
| Extraction Quality | garbage/empty text | readable but truncated/boilerplate | clean, structured, complete |
| Duplicate Suppression | dupes counted as corroboration | exact dupes clustered | near-dupes/source families clustered |
| Conflict Handling | conflict invisible | flagged but unresolved in synthesis | both chains built, confidence adjusted |
| Claim-to-Citation Coverage | claims without evidence ids | bucket-level ids | span-level entailment per claim |
| Citation Validity | dead/wrong URLs | URLs live, loosely support | URLs live and directly support claims |
| Artifact Completeness | files missing | all 11 files, fields sparse | all files, all fields populated |
| Failure Transparency | silent failures | failures logged, status misleading | failures logged AND status/stop_reason honest |
| Bounded Self-repair | unbounded retry / none where needed | advisory feedback only | executed bounded repair improving outcome |
| Reproducibility | cannot re-run | re-runnable, nondeterministic parts unrecorded | fully re-runnable from recorded command+inputs |
| Latency / Tool Calls / Cost | n/a | recorded partially | elapsed_ms per request + wall clock recorded |
| External Fallback Dependence | fallback needed AND unlabeled | fallback needed, labeled | engine sufficient, no fallback |

Scoring notes:
- "unavailable" is used when the engine records nothing measurable (e.g. cost: no token/cost concept exists).
- Scores must cite artifact paths (benchmarks/<ID>/... or runs/<run_id>/...).
- Aggregate scorecard: benchmark_scorecard.json / .md.
