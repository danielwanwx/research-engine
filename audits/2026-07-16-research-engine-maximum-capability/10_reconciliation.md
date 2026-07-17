# 10 — Reconciliation (Phase 6)

Both reports were completed and sealed before either side read the other (observer seal: 2026-07-16T20:34:29Z; primary conclusions written 20:30–21:15Z window per file mtimes). Format: finding / primary view / observer view / agreement / additional evidence / final disposition.

| # | Finding | Primary view | Observer view | Agreement | Final disposition |
|---|---|---|---|---|---|
| 1 | Audit-log timestamp integrity (obs F-1) | commands.jsonl / decision_log.jsonl entries were written in batches with estimated timestamps | "retrospective and fabricated"; declared 35-min window spans 8 min of disk mtimes; no real-time execution journal exists | **Agree (primary concedes)** | Accepted as an audit-process defect. Authoritative timeline = engine artifacts' own `generated_at` fields + file mtimes, both machine-written; commands.jsonl remains valid for *what* ran (cross-checked against run artifacts) but not *when precisely*. Timeline claims in this audit carry reduced confidence. Drives new backlog item RB-019 (engine-side append-only invocation journal) so future audits don't depend on operator diligence. |
| 2 | Silent run-dir overwrites destroyed B1 deep-run and B4 pass-1 bundles (obs F-2) | Disclosed contemporaneously in decision_log; treated as engine-defect evidence | Verified unrecoverable from disk; B4 pass-1 lived 13 seconds | **Agree (convergent)** | Confirmed P0 RB-002. B1/B4-pass1 numbers rest solely on primary notes — flagged as reduced-confidence evidence; all other benchmarks fully disk-verifiable. |
| 3 | run_manifest.benchmark_ids omitted B8 (obs F-3) | Oversight — B8 added after initial manifest | Executed-but-undeclared benchmark | **Agree** | Fixed in final run_manifest.json update; noted as plan-drift instance. |
| 4 | B6 severity (obs F-4) | "1/5 failure modes detected" | Worse: PDF binary is the **highest-scored row in the run (0.90)**; login wall tier=high — active mis-classification, not just silent failure | **Agree — observer's stricter framing adopted** | RB-001 problem statement upgraded: the quality scorer actively *promotes* garbage, it doesn't merely miss it. |
| 5 | Freshness absent (obs F-5) | No published_at anywhere; stale seeds unflagged (B1) | Same, independently, incl. B3/B4 | **Agree (convergent)** | RB-008 confirmed P1. |
| 6 | Conflict chains are lexical noise (obs F-6) | Chains echo the user's query in search-shell pages | Mechanism refined: navigation boilerplate contains *both* polarities, so the same junk rows join both chains | **Agree; observer adds mechanism detail** | RB-015 acceptance updated: chains must exclude rows failing the validity gate AND a row may join at most one side. |
| 7 | Discovery failure (obs F-7/F-8) | Canonical repos absent (B2/B5); exact-name works | Same, independently verified across both passes | **Agree (convergent)** | RB-005/006/007 confirmed. |
| 8 | B8 id collision + metric corruption (obs F-9/F-10) | evidence_id collisions; 404-text rows tier-high | Adds: `unique_evidence_count=10` is arithmetically wrong due to collision | **Agree; observer extends** | RB-003 acceptance tests extended to quality-report counts. |
| 9 | Primary process scores | — | plan_adherence 3, command_logging 2, reproducibility 2, fallback_labeling 5, user_file_safety 5 | **Accepted without dispute** | Reproducibility mitigation: 02_benchmark_plan.json + notes contain exact commands; a scripted benchmark runner (part of RB-010) is the durable fix. |

## Unresolved disagreements
None on substance. One framing difference is preserved rather than erased: the observer labels the log timestamps "fabricated"; the primary characterizes them as "batch-reconstructed estimates." Both descriptions are recorded; the operational consequence (timeline confidence downgraded, RB-019 created) is identical under either framing.

## Effect on confidence labels
- All engine-defect findings: **FACT** (independently double-verified from artifacts).
- B1 deep-run specifics and B4 pass-1 status: downgraded to **FACT (single-witness)** — disk evidence destroyed by the engine's own overwrite behavior.
- Audit timeline durations: **UNKNOWN precision** (see #1).
