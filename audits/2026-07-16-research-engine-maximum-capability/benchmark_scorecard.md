# Benchmark Scorecard (human-readable; data: benchmark_scorecard.json)

| ID | Benchmark | Headline (0–5) | One-line verdict |
|---|---|---|---|
| B1 | Fast-moving market (DRAM/HBM) | **2** | Real-time quotes work; stale seeds unflagged; claims cite junk rows |
| B2 | Deep technical (vLLM vs SGLang) | **1** | Zero technical content; canonical repos never found even after repair |
| B3 | Contested topic (oversupply vs shortage) | **2** | Conflict flag fires but chains are query echoes; confidence unadjusted |
| B4 | Niche, no pack (JSON Canvas) | **1** | Honest hard-fail, then junk; repair overwrote pass-1 artifacts |
| B5 | GitHub survey (deep research agents) | **1** | sort=updated noise; no license/maintenance fields |
| B6 | Adversarial sources | **1** | 1 of 5 failure modes detected; PDF binary scored tier-high |
| B7 | Longitudinal rerun | **3** | Same-day cache works; no TTL, no diff; overwrote B1's run dir |
| B8 | Mixed formats | **1** | evidence_id collisions; '404: Not Found' rows tier-high |

**Median headline: 1/5.** Consistent strengths across all runs: artifact completeness (5), latency telemetry (5), explicit stop reasons on hard failures, safety/redaction. Consistent weaknesses: self-repair (0), soft-failure transparency (1), claim grounding (1), freshness (1), discovery (1).

All scores trace to benchmarks/<ID>/notes.md with artifact paths; commands in commands.jsonl; rubric in 02_benchmark_rubric.md.
