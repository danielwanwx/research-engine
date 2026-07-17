# Structured target intelligence contract

Structured target mode is an additive Research Engine mode for current software-engineering job and interview evidence. It does not claim universal company support. Ordinary topic-only runs keep the existing artifacts and scoring behavior.

## Input

The API accepts a `ResearchTarget` or mapping. The CLI activates the same contract when any `--target-*` flag is present and rejects incomplete tuples rather than falling back to generic research.

```json
{
  "schema_version": "research_target.v1",
  "company": "Stripe",
  "role_family": "software_engineering",
  "role_title": "Staff Backend Engineer",
  "level": "staff",
  "geography": "US",
  "team": ""
}
```

Required fields are `company`, `role_family`, `role_title`, `level`, and `geography`. `target_key` is a deterministic normalization of that complete tuple.

```bash
research-engine run "Stripe Staff Backend Engineer US" \
  --pack interview_prep \
  --target-company Stripe \
  --target-role-family software_engineering \
  --target-role-title "Staff Backend Engineer" \
  --target-level staff \
  --target-geography US \
  --cache-dir state/research-cache \
  --output runs
```

## Discovery and verification order

1. Probe registered official ATS endpoints, then dynamic Greenhouse, Ashby, and Lever board slugs.
2. Fetch the maintained company matrix's official careers search URL when present and follow job-detail links on verified company domains.
3. Use xAI Responses API Web Search and X Search as an optional broad discovery fallback when `GROK_API_KEY` or `XAI_API_KEY` is present.
4. Re-fetch every xAI citation. Model prose is discarded. A citation row stays `discovery_only`; only its separately fetched final URL can enter deterministic claim gates.

No connector logs or writes API keys. Public fetches do not bypass login, paywall, bot, or access controls.

## Evidence output

Each structured row in `evidence.jsonl` has `schema_version: target_evidence.v1` and additive fields:

- `canonical_url`, `final_url`, `is_final_page`, `current_status`, `published_at`, `captured_at`
- `source_class`: `official_jd`, `official_company_material`, `community_report`, `expert_guide`, `generic_resource`, or `discovery_only`
- `target`, `target_key`, and per-dimension `target_match`
- `claim_fitness.disposition`: `accepted`, `background_only`, `discovery_only`, `rejected`, or `duplicate`
- `claim_fitness.eligible_claims` and deterministic `rejection_reasons`
- `independence_key`, `content_hash`, and bounded `text_excerpt`

Wrong-company, wrong-role, wrong-level, wrong-geography, search, landing, stale/closed, non-final, unverified-host, blocked, insufficient, generic, and duplicate rows cannot support target claims. A row cannot self-authorize by setting `source_kind=official_job_posting`; its final host must match the target's verified company domains or a supported ATS host paired with the exact company.

## Claim and loop output

`claim_review.json` uses `target_claim_review.v1`:

- `current_official_role` requires one active, final, fetched official JD compatible with the full target tuple.
- `interview_loop` requires one official company process page or two fresh, independent, target-matched reports.
- `public_discussion_signals` remains `hypothesis_only` below two independent fresh reports.

Support levels are `baseline_only`, `role_calibrated`, `company_calibrated`, and `company_role_calibrated`. No current final official JD means overall `status: unsupported`, even if background material exists. Thin target runs stop with `target_evidence_threshold_not_met` and `complete_with_review_required` when collection itself succeeded.

`run_manifest.json` adds:

```json
{
  "artifact_contract": "target_intelligence.v1",
  "target": {"target_key": "stripe|software_engineering|staff_backend_engineer|staff|us"},
  "target_outcome": {"status": "unsupported", "support_level": "baseline_only"}
}
```

Operational run status remains separate from target calibration. Missing xAI credentials degrade only the dynamic fallback and are recorded as a connector warning. ATS or company fetch failures never become evidence. Zero executable/fetched rows still use the existing operational failure states.

## Consumer compatibility

LoopCoach must read only runs with `artifact_contract == target_intelligence.v1`, require an exact `target.target_key`, and use only evidence whose `claim_fitness.disposition == accepted` and whose claim ID is listed in `eligible_claims`. It must use `target_outcome.support_level` as the calibration ceiling. Legacy artifacts, mismatched target keys, missing final JDs, and `baseline_only` outcomes must not produce target-calibrated coaching.

The maintained `software_engineering_company_matrix.v1` contains 28 companies and verified official domains. Companies outside the matrix still receive dynamic ATS probes and xAI discovery; absence from the matrix is not treated as support.

## Job-market profile is a separate aggregate contract

`job_market` does not weaken or replace the structured single-target contract above.
It requires an explicit `research_scope.v1` with `as_of`, geography, role terms,
levels, and a bounded company list. The runner expands official discovery per company
and writes `job_market_snapshot.json`.

For quantitative snapshots, geography, role terms, and levels are singleton axes;
companies are the only bounded multi-value axis. This prevents a snapshot from
claiming coverage for role/level/geography combinations that were not collected.

The snapshot counts active, closed, duplicate, rejected, and unknown-status rows as
mutually exclusive outcomes. Active counts require a current final official JD that
matches the scope. Coverage exposes requested, checked, failed, and unsupported
companies with an honest denominator. A company is checked only when at least one
official ATS or careers source was actually retrieved; total transport failure is
reported as failed rather than as zero openings. Every normalized field points back to
evidence IDs. `trend` is always unavailable unless a comparable prior snapshot is
supplied; one point-in-time run cannot support a hiring-trend claim.
