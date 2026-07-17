# B3 — Contested topic (DRAM oversupply vs shortage)

- Command: `... run "DRAM oversupply glut inventory correction versus shortage tight supply 2027 outlook" --pack auto --depth deep --web-search-pages --source-timeout-seconds 30` (11.6s)
- Run dir: `runs/2026-07-16-dram-oversupply-glut-inventory-correction-versus-shortage-tight-` (note: run_id silently truncated mid-word — slug truncation)
- Result: complete, 10 rows (same composition as B1: 4 quotes, 2 stale seeds, 4 junk search pages).

## Conflict handling findings
- `availability_pressure` conflict flag FIRED with support ids [ev-0005,0008,0009,0010] and oppose ids [ev-0006,0008,0009]. Mechanism exists and is recorded — genuine differentiator vs naive pipelines.
- **But the chains are contaminated and self-referential**: ev-0008 (HN search shell) and ev-0009 (GitHub search page) appear in BOTH chains because the fetched search pages echo the user's own query terms ("oversupply glut … shortage tight supply"). The engine detected a "conflict" largely between copies of the question itself.
- No genuine oversupply-side source was ever collected (no bearish article exists in the run). Term co-occurrence ≠ opposing evidence chains.
- **Synthesis ignored the conflict**: stance `supported`, confidence `medium`, action_bias `constructive_but_verify_price_and_valuation`. Confidence is computed only from supported-claim counts (synthesis.py:33-37); conflict_flags never feed into stance/confidence. The loop check merely warns.
- No abstention concept; no per-claim uncertainty.

## Rubric
Task understanding 2 (routed to memory_cycle on term match; "versus" framing lost) · Source discovery 1 (no attempt to find opposing sources) · Primary ratio 3 · Freshness 1 · Relevant yield 2 · Diversity 2 · Extraction 2 · Dup 3 · **Conflict handling 2** (flag exists; chains junk-contaminated; synthesis unaffected) · Claim-citation 1 (claims again cite junk rows ev-0009/0010) · Citation validity 2 · Artifacts 5 · Failure transparency 1 · Self-repair 0 · Reproducibility 4 · Latency 5 · Cost unavailable · Fallback n/a.

Headline per plan rubric: **2/5** (flag raised but no usable support/opposition chains, confidence uncalibrated).
