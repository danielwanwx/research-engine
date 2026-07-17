# M2 General Research Capability Implementation Plan

**Date:** 2026-07-16

**Design:** `docs/superpowers/specs/2026-07-16-m2-general-research-capability-design.md`

**Delivery target:** Complete M1 and M2, not a prototype of isolated GitHub search.

## Execution Rules

- Preserve every existing dirty-worktree change. Do not reset, checkout, clean, or
  rewrite unrelated files.
- Use test-first boundary changes. A phase is complete only when its focused tests,
  full suite, Ruff, and relevant eval gates pass.
- Keep the zero-dependency core. Optional provider/PDF integrations must degrade
  honestly when unavailable.
- Do not make search snippets, failed fetches, stale current-state evidence, or job
  landing pages claim-eligible.
- Do not create benchmark-specific branches in production code.
- Do not commit or push mixed user changes. Record exact changed files and ask for a
  human gate before any repository-wide commit.

## Phase 0 — Baseline and Worktree Guard

### Task 0.1: Record the implementation baseline

**Read:**

- `git status --short`
- current M0 review records
- current target-intelligence docs and tests
- `runner.py`, `quality.py`, `synthesis.py`, `loop.py`, `execution.py`

**Run:**

```bash
make check PYTHON=/opt/homebrew/bin/python3.10
make eval PYTHON=/opt/homebrew/bin/python3.10
git diff --check
```

**Record:**

- test and eval counts;
- dirty files and untracked paths;
- M0 artifact contracts that must stay compatible;
- an implementation decision log under the existing audit directory.

**Acceptance:** Baseline is green or any pre-existing failure is isolated and recorded
before implementation begins.

## Phase 1 — Planning and Profile Routing (RB-006 foundation)

### Task 1.1: Add explicit research scopes and facet plans

**Create:**

- `src/research_engine/planning.py`
- `tests/test_planning.py`

**Modify:**

- `src/research_engine/models.py`
- `src/research_engine/packs.py`
- `src/research_engine/runner.py`
- `src/research_engine/cli.py`
- `tests/test_packs.py`
- `tests/test_runner.py`

**Test first:**

1. profile routing selects generic, technical, market-landscape, and job-market plans;
2. legacy `query_templates` normalize into the new facet contract;
3. query IDs are unique and deterministic within a run;
4. quick/deep/audit budgets cannot exceed design caps;
5. `--scope-file` validates `research_scope.v1` and rejects ambiguous/incomplete job
   quantitative scope;
6. planned query/facet IDs propagate to collection requests;
7. existing pack and structured-target routing stays unchanged.

**Implement:**

- `ResearchScope` validation without a schema dependency;
- profile selection from explicit scope, explicit pack, then existing pack intent;
- deterministic facet templates and budgets;
- backwards-compatible query-plan fields plus the new facet/query list.

**Acceptance:** A dry run for each profile writes a complete, bounded, executable plan,
and existing dry-run artifacts remain readable by old consumers.

### Task 1.2: Make planned and executed queries reconcile

**Modify:**

- `src/research_engine/models.py`
- `src/research_engine/execution.py`
- `src/research_engine/runner.py`
- `tests/test_execution.py`
- `tests/test_runner.py`

**Test first:**

- execution records contain pass, facet, and query IDs;
- every planned query is executed or records an explicit skip/failure reason;
- request count and query-plan reconciliation are deterministic;
- query budgets remain bounded when multiple connectors serve one facet.

**Acceptance:** The B2 fixture proves that per-project queries are actual connector
requests, not decorative plan entries.

## Phase 2 — General Web Discovery and Canonical Refetch (RB-005)

### Task 2.1: Implement the web-search connector

**Create:**

- `src/research_engine/connectors/web_search.py`
- `tests/test_web_search.py`

**Modify:**

- `src/research_engine/connectors/__init__.py`
- `src/research_engine/runner.py`
- `src/research_engine/cli.py`
- `src/research_engine/security.py`
- `docs/connector-support.md`

**Test first:**

1. the anonymous provider sends no authorization header;
2. configured SearXNG uses only the explicit endpoint;
3. provider `none` makes no network request;
4. result limits and optional fields are bounded;
5. malformed, quota, rate-limit, and transport failures produce sanitized warnings;
6. normalized rows are `discovery_only` and never claim-eligible;
7. query-plan artifacts disclose the selected provider and query boundary;
8. structured target runs do not silently add generic search.

**Implement:** Provider adapters inside one `web_search` connector. Reuse the approved
AnySearch transport design where its current official contract is verified. Do not add
a second top-level retrieval framework.

### Task 2.2: Refetch canonical candidate URLs

**Modify:**

- `src/research_engine/runner.py`
- `src/research_engine/connectors/web.py`
- `src/research_engine/quality.py`
- `tests/test_runner.py`
- `tests/test_quality.py`
- `tests/test_web_safety.py`

**Test first:**

- duplicate candidate URLs refetch once;
- redirects are revalidated against SSRF policy;
- the refetched row records its discovery evidence and query lineage;
- failed refetches remain in lineage but cannot support claims;
- refetch count obeys depth budget;
- snippets cannot appear in claim or matrix evidence IDs.

**Acceptance:** B4 finds the JSON Canvas specification repository and adopter pages
without pack seeds in the deterministic fixture; a live smoke passes when the selected
provider is available.

## Phase 3 — GitHub Intelligence (RB-007)

### Task 3.1: Correct repository retrieval and metadata

**Modify:**

- `src/research_engine/connectors/github_public.py`
- `src/research_engine/doctor.py`
- `tests/test_github_public.py` or the existing connector test module
- `tests/test_doctor.py`

**Test first:**

- search omits `sort=updated` and keeps raw API order;
- license SPDX, archived, pushed/updated, default branch, topics, stars, forks, and
  issues survive normalization;
- optional environment auth is redacted and doctor distinguishes unavailable,
  unauthenticated, and authenticated states;
- audit enrichment is bounded and degrades on rate limits.

### Task 3.2: Add deterministic repository ranking

**Create or modify:**

- `src/research_engine/relevance.py`
- GitHub connector and tests

**Test first:** Canonical relevant repositories outrank zero-star updated noise; archived
projects receive a penalty; raw rank remains observable; no star threshold alone can
override topical mismatch.

**Acceptance:** B5 top 12 contains the canonical projects required by the audit with
license and maintenance fields populated.

## M1 Checkpoint

Run focused tests, full tests, Ruff, diff check, and deterministic B2/B4/B5 evaluation.
Run live generic and technical smokes when external services are reachable. Write an M1
checkpoint record. Do not begin M2 if a P0/P1 discovery or claim-eligibility regression
is open.

## Phase 4 — Freshness and As-of (RB-008)

### Task 4.1: Add date extraction and freshness classification

**Create:**

- `src/research_engine/freshness.py`
- `tests/test_freshness.py`

**Modify:**

- `src/research_engine/connectors/web.py`
- `src/research_engine/quality.py`
- `src/research_engine/runner.py`
- `src/research_engine/cli.py`
- relevant pack fixtures

**Test first:**

1. connector-native, JSON-LD, meta, time-element, and conservative URL dates follow
   precedence;
2. malformed or ambiguous dates remain undated;
3. `--as-of` is validated and recorded;
4. fresh/stale/undated/not-applicable statuses and age are correct at boundaries;
5. stale evidence remains observable but cannot ground a current claim requiring a
   freshness window;
6. current job claims reject closed or stale rows.

**Acceptance:** B1 flags the dated TrendForce fixture as stale for a 30-day window and
cannot produce a stale-only current supported claim.

## Phase 5 — Extraction and Stable Chunks (RB-011)

### Task 5.1: Separate transport from extraction

**Create:**

- `src/research_engine/extraction.py`
- `tests/test_extraction.py`

**Modify:**

- `src/research_engine/connectors/web.py`
- `src/research_engine/models.py`
- `tests/test_connectors.py`

**Test first:**

- HTML boilerplate is bounded while meaningful headings and paragraphs survive;
- table rows remain structured and bounded;
- long documents create stable chunks with parent provenance;
- JSON content keeps structured evidence;
- PDF adapter success produces text chunks;
- unavailable or failed PDF extraction produces explicit invalid evidence, never
  decoded binary;
- malicious or oversized content remains bounded.

**Implement:** Keep stdlib HTML/JSON support. Add an adapter for an allowlisted local
`pdftotext` and an optional Python PDF extra only if it does not become a core
dependency.

**Acceptance:** B8 preserves the fixture table and either extracts the PDF fixture or
marks it explicitly invalid; a 100k-character fixture produces multiple stable chunks.

## Phase 6 — Relevance, Facet Coverage, and Diversity (RB-012)

### Task 6.1: Add deterministic relevance scoring

**Create or complete:**

- `src/research_engine/relevance.py`
- `tests/test_relevance.py`

**Modify:**

- `src/research_engine/quality.py`
- `src/research_engine/runner.py`
- `src/research_engine/artifacts.py`

**Test first:**

- relevance and quality remain separate fields;
- invalid content always has zero claim utility regardless of relevance;
- title, body, entity, and facet contributions are inspectable;
- canonical on-topic fixtures outrank irrelevant authoritative fixtures;
- duplicated/same-family evidence cannot fill the top preview;
- `facet_coverage.json` reports required-facet relevant yield and missing facets.

**Acceptance:** B2 and B5 relevant yield improves without weakening M0 validity gates;
market and job fixtures expose honest coverage gaps.

## Phase 7 — Network Resilience and Etiquette (RB-013)

### Task 7.1: Add bounded transport policy

**Modify:**

- `src/research_engine/execution.py`
- `src/research_engine/connectors/web.py`
- `src/research_engine/models.py`
- `tests/test_execution.py`
- `tests/test_web_safety.py`

**Test first with injected clock/random/transport:**

- exponential schedule and jitter remain within caps;
- Retry-After is honored only within the overall deadline;
- per-host concurrency/delay is enforced;
- robots allow/deny decisions are cached and recorded;
- honest UA is used;
- redirect SSRF checks still apply;
- rate-limit, robots denial, and retry exhaustion are distinct statuses.

**Acceptance:** No real sleeps or network calls are required by deterministic tests;
B6 remains 5/5 and execution artifacts explain transport decisions.

## Phase 8 — One-pass Repair (RB-009)

### Task 8.1: Implement failure-to-repair mapping

**Create:**

- `src/research_engine/repair.py`
- `tests/test_repair.py`

**Modify:**

- `src/research_engine/runner.py`
- `src/research_engine/loop.py`
- `src/research_engine/artifacts.py`
- `tests/test_runner.py`
- `tests/test_loop.py`

**Test first:**

1. only failed required facets are repaired;
2. zero sources enables the configured search path;
3. low relevance broadens/simplifies queries;
4. stale yield adds current/as-of terms;
5. source concentration adds primary/independent-source queries;
6. failed refetch uses only the next bounded candidates;
7. repair never relaxes validity, freshness, target, robots, or SSRF rules;
8. a progress fingerprint permits exactly one useful pass;
9. identical failure stops with `repair_no_progress`;
10. pass-1 records remain intact in final artifacts.

**Acceptance:** B4 recovers in one run with `repair_record.json`; a no-progress fixture
stops deterministically without a third pass.

## Phase 9 — Independent Conflict Chains (RB-015)

### Task 9.1: Model source families and claim chains

**Create:**

- `src/research_engine/conflicts.py`
- `tests/test_conflicts.py`

**Modify:**

- `src/research_engine/quality.py`
- `src/research_engine/synthesis.py`
- `src/research_engine/loop.py`
- pack fixtures and synthesis tests

**Test first:**

- canonical publisher/organization/repository generates a stable independence key;
- syndicated and duplicate content share a family when deterministically known;
- two independent supporting rows can satisfy a configured corroboration rule;
- distinct independent opposition lowers stance/confidence;
- same-family copies, duplicated chunks, query echoes, and self-conflict do not form
  independent chains;
- insufficient polarity evidence remains `needs_more_evidence`.

**Acceptance:** B3 records separate evidence chains and cannot retain high-confidence
support under distinct eligible opposition.

## Phase 10 — Generic Market and Job-market Profiles

### Task 10.1: Add profile packs and coverage contracts

**Create:**

- package and project-overlay packs for `technical`, `market_landscape`, and
  `job_market` following existing pack conventions;
- deterministic B9 and B10 fixtures;
- `tests/test_market_profile.py`;
- `tests/test_job_market.py`.

**Modify:**

- `src/research_engine/packs.py`
- `src/research_engine/planning.py`
- `src/research_engine/runner.py`
- pack validation tests

**Test first:**

- each profile emits its required facets and source strategy;
- technical routing does not force GitHub on nontechnical topics;
- market claims carry geography/definition/as-of when available;
- quantitative job claims require explicit scope;
- existing interview-prep target behavior remains stricter and unchanged.

### Task 10.2: Produce point-in-time job snapshots

**Create:**

- `src/research_engine/job_market.py`
- `tests/test_job_market.py`

**Modify:**

- `src/research_engine/connectors/job_discovery.py`
- `src/research_engine/company_matrix.py`
- `src/research_engine/runner.py`
- `src/research_engine/artifacts.py`
- `docs/target-intelligence.md`

**Test first:**

- official active roles dedupe by canonical/requisition identity;
- closed, landing, search, wrong-company, wrong-role, wrong-geography, and unknown
  rows do not count as active;
- normalized company, role, level, geography, skill, and disclosed salary fields are
  traceable to evidence IDs;
- coverage records requested, checked, failed, and unsupported companies/sources;
- all aggregates reconcile to accepted rows;
- no trend conclusion is emitted without a comparable prior snapshot.

**Acceptance:** B10 produces a coherent scoped snapshot and honest coverage denominator.

## Phase 11 — Evaluation, Documentation, and Final Review

### Task 11.1: Expand the versioned evaluation suite

**Modify/create:**

- `evals/v2/` fixtures and expected outcomes for B1-B10;
- `src/research_engine/eval.py` with backwards-compatible M0 output fields;
- `tests/test_eval.py`;
- audit scorecards and benchmark notes.

**Required gates:**

- offline B1-B10 pass;
- M0 9/9 validity checks remain green;
- 5/5 invalid probes remain detected;
- all existing tests pass;
- Ruff and `git diff --check` pass;
- generic, technical, market, and job live smokes either pass or record a specific
  external limitation without altering offline acceptance.

### Task 11.2: Update user and connector documentation

**Modify:**

- `README.md`
- `docs/connector-support.md`
- `docs/target-intelligence.md`
- `docs/m2-usage.md`

Document:

- third-party query boundaries and opt-out;
- profile selection and scope files;
- as-of/freshness semantics;
- discovery versus claim evidence;
- repair limits;
- job snapshot coverage limitations;
- optional PDF and authenticated GitHub capabilities;
- exact quick-start commands for technical, market, and job research.

### Task 11.3: Independent Fable review loop

Fable reviews correctness, security, compatibility, benchmark validity, and scope.
Every P0-P2 finding receives a root-cause fix and another review round. Record the
review under:

```text
audits/2026-07-16-research-engine-maximum-capability/
13_m1_m2_implementation_review.md
```

**Final success:** No unresolved P0/P1 findings, all deterministic gates green, and no
M0 or structured-target regression.

## Fable Delegation Contract

```text
Task: Implement Research Engine through the approved M2 result

Use Loop Engineering. This is a bounded M1 -> M2 delivery, not open-ended exploration.

Goal:
Implement the approved M2 design so unseeded technical, generic market, and scoped
point-in-time job-market questions produce relevant, fresh, auditable evidence bundles
with one bounded repair pass and independent conflict chains.

Input scope:
- docs/superpowers/specs/2026-07-16-m2-general-research-capability-design.md
- docs/superpowers/plans/2026-07-16-m2-general-research-capability-implementation-plan.md
- current dirty worktree, approved M0, structured target intelligence
- audit backlog and B1-B10 fixtures

Execute:
1. Record baseline and preserve every pre-existing change.
2. Implement Phase 1 through Phase 11 in order.
3. Stop at the M1 checkpoint until its gates pass, then continue directly to M2.
4. Use focused tests first, then full checks and evals.
5. Record decisions, external limitations, findings, and fixes.

Checks:
- phase-specific tests and artifact assertions
- complete unit suite and Ruff
- git diff --check
- offline B1-B10 plus preserved M0 gates
- bounded live smokes where providers are reachable
- secret/redaction, SSRF, robots, discovery-only, freshness, and no-overwrite regressions

Feedback rules:
- failed gate -> repair the owning shared boundary, then rerun focused and full checks
- external service unavailable -> keep deterministic fixture coverage and record the
  limitation; do not weaken evidence gates
- P0-P2 review finding -> fix root cause and request another review
- required destructive operation, paid service, credential exposure, or scope expansion
  -> stop and request human approval

Records:
- implementation decision log
- eval scorecards and smoke paths
- changed-file inventory
- 13_m1_m2_implementation_review.md

Stop conditions:
- success: every M2 acceptance gate passes and final review has no unresolved P0/P1
- stop and report: destructive worktree conflict, undisclosed paid dependency, account
  mutation, unsafe credential handling, or repeated no-progress blocker

Non-goals:
- multi-agent runtime, required LLM planner/judge, embeddings, vector database,
  monitoring daemon, M3 longitudinal diff, account mutation, paywall/login bypass

Final report:
- capabilities delivered by milestone
- changed files and artifacts
- exact tests/evals/smokes with results
- review rounds and fixes
- remaining M3 risks
```
