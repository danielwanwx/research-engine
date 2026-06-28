# Research Engine Release Readiness Eval - 2026-06-27

This eval dogfoods Research Engine on two real research tasks:

1. AI capex sustainability across Microsoft, Meta, Alphabet, and Amazon.
2. Micron / MU earnings sustainability, stock pressure, and DRAM/HBM cycle evidence.

The goal is to score whether the current engine is ready to release as a general-purpose
research tool, using loop-engineering criteria rather than a single happy-path run.

## Loop Contract

Goal:
Evaluate whether Research Engine can turn a natural research request into useful, auditable
evidence artifacts and correctly stop, warn, or fail when evidence is missing.

Input scope:
- Current repo at `/Users/danielwan/Project/research-engine`.
- Live public connectors available locally.
- External JSONL evidence files created for authorized/manual evidence ingestion.
- Independent sub-agent review of repo and eval artifacts.

Execute steps:
1. Run naive user requests without curated evidence.
2. Run the same domains with external evidence to test connector-assisted quality.
3. Inspect `run_manifest.json`, `evidence.jsonl`, `claim_review.json`, `evidence_quality.json`,
   `loop_record.json`, and `research_report.md`.
4. Ask an independent agent to score release readiness.
5. Fix defects that the eval exposes when the fix is local and bounded.
6. Re-run tests and representative smoke cases.

Checks:
- Naive run should not claim success when it returns zero evidence.
- Curated run should produce traceable evidence and quality scores.
- Loop record should produce stop reasons and feedback actions.
- Financial claim review should not confuse stock quotes with memory-contract pricing.
- Packaged default packs should match project packs.

Stop conditions:
- Success: artifacts and tests prove the release score and remaining blockers.
- Stop and report: engine remains alpha because default collection is too thin or checks are too weak.

## Case Results

| Case | Run path | Status | Rows | Loop status | Notes |
| --- | --- | ---: | ---: | --- | --- |
| AI capex naive | `/tmp/research-engine-anton-eval-20260627/ai-capex-naive-status-fix/...` | `failed_no_rows` | 0 | `blocked` | Correctly stops after no evidence. Earlier eval exposed a bug where this was `complete_empty`; fixed. |
| AI capex curated deep | `/tmp/research-engine-anton-eval-20260627/ai-capex-curated-deep-fixed/...` | `complete` | 6 | `complete_with_review_required` | Evidence ingestion works, but generic research lacks pack-specific claims, so loop now requires analysis before decision use. |
| MU naive | `/tmp/research-engine-anton-eval-20260627/mu-naive/...` | `complete_with_warnings` | 3 | `complete_with_review_required` | Finance quotes work, but web seed timed out; default evidence is too shallow. |
| MU curated deep fixed | `/tmp/research-engine-anton-eval-20260627/mu-curated-deep-fixed/...` | `complete_with_warnings` | 11 | `complete_with_review_required` | Useful evidence pack; flags conflict and connector warning. |

## Evidence Observations

AI capex curated run collected evidence on:
- Big-tech 2026 capex plans rising sharply.
- Microsoft stock pressure from AI capex intensity.
- Meta 2026 capex guidance increase and investor pushback.
- Goldman-style multi-year AI infrastructure capex thesis.
- Memory/HBM cost pressure as a meaningful share of hyperscaler capex.

MU curated run collected evidence on:
- MU, SNDK, SK hynix, and Samsung quote snapshots.
- TrendForce 2Q26 DRAM/NAND contract price pressure.
- Micron fiscal Q3 2026 earnings and guidance coverage.
- Micron capex ramp to meet demand.
- Market pressure from high AI-trade expectations.
- Valuation discount from memory-cycle risk.
- Reported DRAM shortage persistence beyond 2026.

## Defects Found And Fixed

1. Zero-row runs could report `complete_empty`.
   - Fix: `run_status()` now returns `failed_no_rows` whenever executable sources return zero rows.
   - Added regression: `test_runner_marks_empty_connector_results_as_failed_no_rows`.

2. Generic evidence runs could pass all loop checks despite no claim-specific grounding.
   - Fix: generic stance `evidence_collected_needs_analysis` now makes `claim_grounding` warn.
   - Added regression: `test_generic_evidence_requires_analysis_before_decision_ready`.

3. Memory-cycle pricing claim could match stock quotes via the broad keyword `price`.
   - Fix: narrowed `price_acceleration` keywords to contract/ASP/price-increase language.

4. Project packs and package default packs could drift.
   - Fix: synchronized `packs/memory_cycle.json` and `src/research_engine/default_packs/memory_cycle.json`.
   - Added regression: `test_project_packs_match_packaged_defaults`.

## Independent Agent Review

Independent review score before the bounded fixes above: `62 / 100`.

Review recommendation:
Alpha only. Do not release as a general-purpose deep research tool yet. The strongest position is
developer alpha / research harness prototype.

Key independent findings:
- Naive default experience is not reliable enough for broad financial/industry research.
- Curated external evidence path works well.
- Loop artifacts are a real differentiator.
- Financial research safety needs stronger semantic claim matching.
- Release hygiene still needs CI, remote setup, CONTRIBUTING/SECURITY, and connector docs.

## Updated Score After Fixes

Current score: `68 / 100`.

Breakdown:
- Default UX: `13 / 25`
- Curated / connector-assisted quality: `21 / 25`
- Loop engineering: `18 / 20`
- Financial research safety: `10 / 20`
- Release hygiene: `6 / 10`

Verdict:
Research Engine is ready for an alpha release only if positioned as an evidence-first research
loop harness, not a full deep-research crawler.

Recommended positioning:
> Bring your own crawlers. Research Engine turns messy multi-platform data into auditable
> evidence packs, source-quality checks, conflict flags, loop stop reasons, and LLM-ready
> research artifacts.

## Remaining Blockers Before Broader Release

1. Add first-class open-web search / crawler fallback for non-GitHub topics.
2. Improve semantic claim grounding beyond substring keyword matching.
3. Add source diversity gates for broad research tasks.
4. Make optional AgentReach/OpenCLI/browser connectors installable and diagnosable from docs.
5. Add GitHub Actions CI, `.env.example`, `CONTRIBUTING.md`, `SECURITY.md`, and release examples.
6. Make run IDs collision-resistant when the same topic is run repeatedly.
7. Stabilize `web_page` connector against slow official investor-relations pages.

## Verification

Commands run after fixes:

```text
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /tmp/research-engine-py313/bin/python -m pytest -p no:cacheprovider -q
81 passed in 0.15s

env RUFF_CACHE_DIR=/tmp/research-engine-ruff-cache /tmp/research-engine-py313/bin/python -m ruff check src tests
All checks passed!

git diff --check
clean
```
