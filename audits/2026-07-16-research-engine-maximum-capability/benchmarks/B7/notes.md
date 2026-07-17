# B7 — Longitudinal rerun (cache / freshness / diff)

- Commands: same topic run twice, `--depth quick --cache-dir <audit>/fixtures/cache` (run1 1.6s network, run2 0.07s).
- Run dir (both, and also formerly B1's): `runs/2026-07-16-dram-hbm-memory-contract-price-supply-july-2026`

## Findings
- Cache HIT on rerun: both sources `cache_hit`, 0ms — mechanism works within the same day+depth. Telemetry records hits properly.
- **Cache has no TTL/staleness policy**: run2's "regular market price" rows are cache copies — for intraday-moving data the engine serves frozen prices with `cache_hit` noted in collection_execution but nothing in the evidence rows or report marks them as cached/stale.
- **Cache key includes run_date and depth** (execution.py:228-238): cross-day reruns can never hit (cache is effectively same-day only), and quick/deep runs don't share entries. So the cache neither supports longitudinal reuse nor protects against stale reuse — inverted semantics for a research cache.
- **No diff/incremental capability**: no artifact compares run1 vs run2; no change detection, no persistent state across runs (state.py is 30 lines, doctor capabilities only). Capability gap confirmed as predicted.
- **Second confirmed run-dir overwrite**: this benchmark's runs silently replaced the B1 deep-run directory (same run_id derivation, runner.py:113). An 11-file evidence bundle was destroyed by a routine rerun. Incident recorded in decision_log.jsonl; B1 numbers preserved in benchmarks/B1/notes.md captured before overwrite.

## Rubric
Headline per plan rubric: **3/5** (cache hits work; no diff/freshness policy). Reproducibility dimension for the ENGINE: 2 (reruns destroy prior artifacts). Failure transparency 3. Latency 5.
