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

1. For a registered company, use only its configured official ATS/API provider. Amazon uses its public `amazon.jobs` search JSON endpoint; registered custom sites go directly to their official careers route and never fan out across unrelated ATS providers.
2. For an unregistered company, make bounded Greenhouse, Ashby, and Lever probes. Verify the returned board path owns the normalized company token, rank target metadata, and fetch at most four final candidates.
3. Fetch a configured official careers search URL when present and follow only target-ranked detail links on verified company domains.
4. Use xAI Responses API Web Search and X Search as an optional broad discovery fallback when `GROK_API_KEY` or `XAI_API_KEY` is present.
5. Re-fetch every xAI citation. Model prose is discarded. A citation row stays `discovery_only`; only its separately fetched final URL can enter deterministic claim gates.

No connector logs or writes API keys. Public fetches reject credentialed, local, and private-network URLs, revalidate redirects, and bound response bodies. They do not bypass login, paywall, bot, or access controls. Blocked, JavaScript-shell, not-found, and closed bodies are never final evidence.

A configured or dynamically ownership-verified public ATS/API record may remain the canonical official record when its human page is access-blocked or a JavaScript shell, provided the API entry is active and contains the full JD. Explicitly closed/not-found pages override that fallback. This exception never applies to an unverified dynamic slug.

## Evidence output

Each structured row in `evidence.jsonl` has `schema_version: target_evidence.v1` and additive fields:

- `canonical_url`, `final_url`, `is_final_page`, `current_status`, `published_at`, `captured_at`
- `source_class`: `official_jd`, `official_company_material`, `community_report`, `expert_guide`, `generic_resource`, or `discovery_only`
- `target`, `target_key`, and per-dimension `target_match`
- `claim_fitness.disposition`: `accepted`, `background_only`, `discovery_only`, `rejected`, or `duplicate`
- `claim_fitness.eligible_claims` and deterministic `rejection_reasons`
- `independence_key`, `content_hash`, and bounded `text_excerpt`

Wrong-company, wrong-role, unknown or wrong level/geography, search, landing, stale/closed, non-final, unverified-host, blocked, insufficient, generic, and duplicate rows cannot support target claims. Exact role matching is anchored to an official API title, page heading, or final URL slug; role words scattered through a body are only a near match. A row cannot self-authorize by setting `source_kind=official_job_posting`; its final host must match the target's verified company domains or an ATS record with deterministic board-ownership verification. Every rejected row has at least one named rejection reason.

## Claim and loop output

`claim_review.json` uses `target_claim_review.v1`:

- `current_official_role` requires one active, final, fetched official JD with an exact anchored role title and known compatible level and geography. Only an explicitly `unspecified` or `any` target level may omit level matching.
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
