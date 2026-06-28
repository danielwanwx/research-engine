# E2E Validation - 2026-06-27

Status: Clean after blocker fixes

## Goal

Validate that Research Engine can run as an evidence-first research loop for
downstream domain agents, with explicit Loop Engineering controls:

- Context hygiene
- Stop brakes
- Critic separation
- Tool focus

## Local Checks

- `pytest -p no:cacheprovider -q`: 92 passed
- `ruff check --no-cache src tests`: passed
- Changed-file `ruff format --check`: passed
- `git diff --check`: clean

The local test environment used a temporary Python 3.10 venv at
`/private/tmp/research-engine-test-venv` because the system `pytest` was bound to
Python 3.9 and this project requires Python 3.10 or newer.

## CLI E2E Scenarios

Artifacts were written under `/private/tmp/research-engine-e2e-20260627`.

| Scenario | Expected behavior | Result |
| --- | --- | --- |
| Authorized medical billing external JSONL | Collect rows, expose `loop_status`, require review for generic claims | Passed: `status=complete`, `loop_status=complete_with_review_required` |
| External JSONL with sensitive field | Drop sensitive field, warn, no secret leak | Passed: `status=complete_with_warnings`, no leaked test secret |
| Manual/custom connector with sensitive row | Sanitize after normalization, warn, no secret leak | Passed: no leaked test secret |
| No-source generic query | Stop as blocked with explicit feedback | Passed: `status=failed_no_sources`, `loop_status=blocked` |
| Free-text prior authorization policy | Preserve domain evidence, do not false-positive redact | Passed |
| Structured `prior_authorization` field plus auth secret | Preserve domain field, drop real auth key, no secret leak | Passed |

Every inspected run contained the required loop checks in `loop_contract.json`
and `loop_record.json`.

## Independent Agent Findings

Four independent agent reviews were run.

1. Initial review score: 72/100.
   - Blocker: CLI/API exposed `status=complete` without `loop_status`.
   - Blocker: context hygiene did not inspect sensitive strings.

2. Re-review score: 78/100.
   - Prior blockers fixed.
   - New blocker: `Prior authorization: ...` was redacted as an auth header.

3. Narrow sanitizer re-review score: 76/100.
   - Free-text prior authorization fixed.
   - Remaining issues:
     - `prior_authorization` field name was still dropped.
     - `Authorization: OAuth|Digest|ApiKey ...` was not redacted.

4. Final sanitizer re-review score: 86/100.
   - Scoped sanitizer blockers resolved.
   - Recommendation: proceed with Alpha positioning and keep sanitizer hardening
     in the release polish backlog.

Both remaining sanitizer issues were fixed and covered by tests:

- `prior_authorization`, `pre_authorization`, and `preauthorization` fields are
  preserved.
- Real `authorization`, `authorization_header`, and auth-header credentials are
  still redacted.
- `Bearer`, `Basic`, `Token`, `OAuth`, `Digest`, and `ApiKey` authorization
  schemes are redacted.
- Domain-safe keys ending in secret-like suffixes, such as
  `preauthorization_token`, are still dropped.
- Raw AWS access key, GitHub token, and JWT-shaped strings are redacted.

## Current Assessment

Research Engine is now clean for Alpha positioning:

> Evidence-first research loop harness for AI/domain agents.

It should not yet be marketed as a turnkey domain-agent research substrate.
Domain-specific packs, claim specs, source freshness checks, jurisdiction/rule
priority, and real AgentReach/OpenCLI/browser connector E2E still need more
work before high-risk production use.

## Residual Risks

- Sanitizer coverage is stronger but still heuristic.
- `critic_separation` proves separate artifacts/checks, not a fully independent
  process or model.
- Generic packs still produce `complete_with_review_required`; domain agents
  need pack-specific claim specs before decision-ready use.
- Full-project `ruff format --check src tests` still reports older files outside
  this changed set as unformatted.
