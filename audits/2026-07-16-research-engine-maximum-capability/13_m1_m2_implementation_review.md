# M1/M2 Implementation Review

**Date:** 2026-07-16 (America/Los_Angeles)  
**Result:** Approved after four independent review rounds  
**Unresolved findings:** No P0, P1, or P2 findings

## Outcome

The approved M1 → M2 design and implementation plan are implemented. The engine now
supports bounded unseeded generic, technical, market-landscape, and explicitly scoped
point-in-time job-market research while preserving the M0 evidence-validity and
structured-target contracts.

The implementation remains a zero-required-dependency deterministic core. Optional
search, GitHub authentication, browser rendering, and PDF extraction degrade honestly.
No benchmark-specific branch was added to the runtime, and no validity, freshness,
robots, SSRF, or target gate is relaxed by repair.

## Milestone Conformance

### M1

- Deterministic profile routing, `research_scope.v1`, facet/query budgets, query IDs,
  and planned-versus-executed reconciliation.
- Explicit third-party search boundary with AnySearch, configured SearXNG, and `none`.
- Discovery-only snippets followed by bounded canonical refetch with lineage.
- GitHub raw-order preservation, metadata enrichment, and deterministic topical
  ranking.
- Pass/query/facet execution lineage and an M1 checkpoint before M2 work.

### M2

- As-of date extraction and strict freshness-required claim eligibility, including
  rejection of stale, undated, malformed, and future-dated evidence.
- Content-type-aware extraction, stable parent-linked chunks, table/JSON preservation,
  and explicit PDF failure states. Chunks participate in relevance, deduplication,
  conflict analysis, and synthesis instead of being output-only.
- Separate quality and relevance scores, diverse previews, and full required-facet
  coverage including `omitted_by_budget` disclosure.
- Deadline-bounded retries, bounded `Retry-After`, per-host scheduling, cached robots
  decisions, honest user agent, and distinct failure statuses.
- Exactly one repair pass with progress fingerprints and direct bounded canonical
  candidate refetch.
- Independent support/opposition chains that constrain claim verdict and confidence.
- Technical, market-landscape, and job-market packs. Quantitative job scopes use
  singleton geography/role/level axes, a bounded company axis, transport-truthful
  coverage, mutually exclusive terminal company outcomes, and no unsupported trend.
- Versioned offline B1–B10 evaluation with nested M0 acceptance.

## Independent Review Rounds

| Round | Result | Findings and root-cause remediation |
| --- | --- | --- |
| 1 | Rejected | 6 P1 and 2 P2. Replaced self-fulfilling B2/B4/B7/B9 checks with fixture-connector engine/CLI artifact tests; tightened freshness and independent-chain ceilings; disclosed full/omitted facets; moved chunks into analysis; made job axes honest; activated direct canonical repair; normalized network statuses and retry bounds. |
| 2 | Rejected | 1 P1 and 1 P2. Total ATS transport failure now records endpoint telemetry and becomes failed coverage; failed results are not cached as successful checks. The snapshot API reuses the authoritative scope validator. |
| 3 | Rejected | 1 P2. Company coverage now aggregates all passes: any successful retrieval is checked, and a company is failed only when every attempt fails. |
| 4 | Approved | Independent reviewer found no remaining P0–P2 findings. |

## Final Deterministic Gates

- Unit/integration suite: **257 passed**.
- Ruff: **clean**.
- `git diff --check`: **clean**.
- Eval v2: **B1–B10 = 10/10**.
- Nested M0: **9/9 checks**, **5/5 invalid probes detected**.
- Explicit eval v1 rerun: **9/9 checks**, **5/5 invalid probes detected**.
- Independent final verification reproduced the same 257-test, lint, diff, M2, and M0
  results.

The durable v2 result is `m2-eval/scorecard.json`. B2 executes per-project repository
requests and asserts collected repository artifacts; B4 executes search, canonical
fetch, and one repair pass; B7 verifies CLI journals and immutable reruns; B9 executes
all seven market facets and asserts artifact coverage and claim context.

## Live Smoke Results

- AnySearch public contract: available with the expected success envelope.
- Generic JSON Canvas: complete, 20 rows, 3/3 planned queries, no warnings.
- Technical vLLM versus SGLang: complete, 20 rows; both canonical repositories ranked
  first within their project facets with license and maintenance metadata.
- Market landscape: complete with warnings, 36 rows, 2/3 quick facets covered, one
  bounded repair. Two pages were excluded by `robots_denied`; pricing remained an
  explicit gap.
- Scoped Anthropic job snapshot: complete, five official ATS rows observed, 1/1 source
  checked, zero active matches, five explicit rejections, and no trend claim.

Live search rank, robots policy, endpoint availability, and current job inventory are
external state and do not alter offline acceptance.

## Compatibility and Security

- Existing M0 invalid-content probes remain excluded from claims.
- Discovery snippets remain claim-ineligible; redirects still receive SSRF validation.
- Existing runs remain immutable and CLI invocation journals remain redacted.
- The stricter `target_intelligence.v1` single-target contract is unchanged; aggregate
  job-market output uses a separate artifact.
- No credentials, paid services, account mutation, destructive worktree operation, or
  required new dependency was introduced.

## Changed-area Inventory

Major runtime areas: planning, packs, runner, execution, web/web-search/GitHub/job
connectors, freshness, extraction, relevance, repair, conflicts, quality, synthesis,
job aggregation, artifacts, security, CLI, and loop records.

Durable additions: M2 usage and target documentation, mirrored profile packs,
`evals/v2`, B1–B10 fixtures/scorecard, M1 checkpoint, implementation decision log,
benchmark notes, and this review.

## Remaining M3 Risks

- Longitudinal snapshot diff/trend analysis remains intentionally out of scope.
- Search-provider and public ATS availability remain external operational risks.
- General semantic entailment remains deterministic keyword/profile logic rather than
  a required LLM judge.
- Multi-agent runtime, embeddings/vector databases, monitoring daemons, and login or
  paywall bypass remain non-goals.

## Repository State

The pre-existing dirty worktree was preserved. No reset, checkout, clean, commit, or
push was performed during this implementation/review cycle.
