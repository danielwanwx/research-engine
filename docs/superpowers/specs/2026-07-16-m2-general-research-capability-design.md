# M2 General Research Capability Design

**Date:** 2026-07-16

**Status:** Approved for implementation

**Scope:** M1 RB-005/RB-006/RB-007 plus M2 RB-008/RB-009/RB-011/RB-012/RB-013/RB-015, with bounded market-landscape and point-in-time job-market profiles

## Outcome

Advance Research Engine from a trustworthy evidence ledger to a useful, bounded
deep-research backend. A user must be able to start from an unseeded question in
three representative domains:

1. technical and GitHub research;
2. generic market-landscape research;
3. point-in-time job-market research.

The engine must discover candidate sources, execute multiple research facets,
refetch and validate canonical content, measure relevance and freshness, perform
one deterministic repair pass when necessary, and expose independent supporting
and opposing evidence chains. It remains an evidence and verification layer for a
downstream agent; it does not silently convert weak evidence into expert judgment.

## Current Baseline

M0 is the required baseline and must not regress:

- invalid, blocked, binary, and discovery-only content cannot ground claims;
- run directories are immutable and collision-safe;
- evidence identifiers are unique within a run;
- cited opposing evidence calibrates stance and confidence;
- CLI runs have an append-only redacted journal;
- deterministic offline validity evaluation is green.

The implementation begins on a dirty worktree containing approved M0 and structured
target-intelligence work. Existing changes must be preserved. No reset, checkout,
cleanup, or wholesale commit is allowed.

## Design Choice

### Selected: one domain-neutral pipeline with routed connectors and profiles

Keep the existing `Connector.collect(CollectionRequest)` boundary. Add a search
connector whose internal provider is configurable, a deterministic facet planner,
and research profiles that select facets, source types, freshness rules, and
coverage requirements. All domains converge on the same evidence, quality, loop,
and artifact contracts.

This makes GitHub a high-value technical connector rather than the engine's global
search strategy. Generic market and job questions use different source routes while
sharing the M0 trust layer.

### Rejected: separate engines for technical, market, and job research

Separate pipelines would duplicate fetching, validity, identity, journaling,
freshness, and conflict logic. Their evidence semantics would drift and downstream
agents would need three incompatible contracts.

### Rejected: an LLM planner and judge as the M2 core

An LLM can help a downstream agent propose facets later, but making it the required
planner or entailment judge would add nondeterminism and cost before the deterministic
evaluation suite can measure it. M2 uses inspectable templates, scores, and bounded
repair rules.

## Architecture

```text
topic + optional structured scope
        |
        v
profile routing -> facet plan -> connector requests
        |                              |
        |                              v
        |                     discovery candidates
        |                              |
        |                              v
        |                    canonical URL refetch
        |                              |
        v                              v
coverage rules <- normalized evidence + extraction chunks
        |                              |
        v                              v
freshness + relevance + validity + independence
        |
        v
claim/conflict review -> bounded repair decision
        |                       |
        | repair once           | no repair / no progress
        +-----------------------+
        |
        v
auditable artifacts for a downstream agent
```

### Module boundaries

- `planning.py` owns profile routing, facet construction, budgets, and conversion
  from planned facets to connector requests.
- `connectors/web_search.py` owns search-provider transport and normalized discovery
  candidates. It does not make search snippets claim-eligible.
- `runner.py` orchestrates pass 1, optional canonical refetch, checks, and at most
  one repair pass. It does not absorb provider, extraction, or scoring logic.
- `extraction.py` owns content-type dispatch, HTML blocks/tables, PDF adapters, and
  stable chunks.
- `freshness.py` owns date extraction, as-of comparison, and freshness status.
- `relevance.py` owns deterministic query/facet relevance and final evidence order.
- `conflicts.py` owns source independence and claim-level support/opposition chains.
- `repair.py` maps recorded check failures to one bounded second-pass plan.
- `job_market.py` owns job-scope normalization and point-in-time aggregation. It
  reuses official ATS evidence rather than creating a separate collection runtime.
- Existing `quality.py`, `synthesis.py`, `loop.py`, and artifact writers remain the
  integration boundaries for common output.

## Research Profiles

Profiles are source and acceptance strategies, not separate engines.

### `generic`

Required facets: overview, primary sources, current evidence, alternatives, and
risks or counterevidence. It uses public web search and canonical refetch. It may
route to GitHub only when repository intent is explicit.

### `technical`

Required facets: official documentation, canonical repositories, releases or
maintenance, architecture, performance evidence, and limitations. GitHub search is
enabled, but repository metadata never substitutes for technical documentation or
independent benchmark evidence.

### `market_landscape`

Required facets: market definition, companies/products, pricing or monetization,
demand signals, competition, regulation or constraints, and contrary evidence.
Current-state claims require fresh evidence; estimates must retain publisher,
publication date, definition, and geography when available.

### `job_market`

Required facets: official active openings, company coverage, role terms, geography,
level, skills, and compensation when explicitly published. Official ATS/career pages
are primary. Search results and job-board mirrors are discovery-only until the final
official page is fetched and verified.

This profile produces a point-in-time snapshot. It must not claim growth or decline
without a comparable prior snapshot. Longitudinal diff remains M3, although M2
artifacts must be shaped so later snapshots are comparable.

### Existing structured target and interview behavior

The existing complete company/role/level/geography target contract remains intact.
`job_market` is aggregate research and must not weaken the stricter single-target
claim rules.

## Planning and Source Routing — RB-006

### Facet contract

Every executed query is represented in `query_plan.json`:

```json
{
  "facet_id": "pricing",
  "query_id": "q-0004",
  "query": "AI inference platform official pricing 2026",
  "source_types": ["web_search"],
  "required": true,
  "freshness_window_days": 180,
  "max_results": 8,
  "status": "planned"
}
```

Query IDs are unique and stable within a run. `collection_execution.json` records
the query ID and facet ID for every actual request. Planned and executed query counts
must reconcile.

Existing pack `query_templates` remain supported and normalize into facets. New packs
may define `facets` with query templates, accepted source types, freshness rules,
minimum relevant evidence, and whether the facet is required.

### Budgets

Budgets bound cost and query explosion:

| Depth | Planned queries | Results/query | Canonical refetches | Repair |
| --- | ---: | ---: | ---: | ---: |
| quick | <= 3 | <= 5 | <= 8 | 0 or 1 only for zero evidence |
| deep | <= 8 | <= 8 | <= 24 | <= 1 |
| audit | <= 12 | <= 10 | <= 40 | <= 1 |

Profile-specific limits may be lower but never higher without an explicit CLI
override recorded in the manifest.

## Public Web Discovery — RB-005

Add a `web_search` connector with provider adapters behind one result contract.

- `anysearch` is the anonymous default already designed by the repository for
  ordinary public topics.
- `searxng` is supported when an endpoint is explicitly configured.
- `none` is an explicit privacy/offline mode.
- Additional paid providers may be added later without changing planning or evidence
  contracts.

The selected provider and third-party query boundary are visible in the query plan.
The engine never silently fans the same query out to multiple providers.

Search rows have `source_class=discovery_only` and `claim_eligible=false`. The runner
deduplicates their public HTTP(S) URLs, applies existing SSRF protections, and refetches
bounded canonical pages through the web connector. Only successfully fetched and
validated content can become claim-eligible.

Partial provider failure retains successful facets and produces warnings. Total
discovery failure is eligible for the single repair rule; it never turns snippets into
evidence.

## GitHub Intelligence — RB-007

GitHub repository search must:

- omit the current `sort=updated` bias and use best-match retrieval;
- retain license SPDX ID, archived state, pushed/updated timestamps, stars, forks,
  open issues, language, topics, and default branch;
- calculate a deterministic ranking from topical relevance, maintenance recency,
  adoption signals, and an archived penalty;
- preserve raw API rank separately from engine rank;
- at audit depth, optionally enrich only a bounded top set with latest release and
  contributor information;
- use optional environment authentication without writing tokens or headers to
  artifacts;
- distinguish repository metadata from independent technical evidence.

B5 succeeds only when canonical deep-research repositories rank in the top set with
license and maintenance fields populated.

## Freshness and As-of Semantics — RB-008

Every run has an explicit `as_of` date, defaulting to the run date and overridable by
CLI/API. Date extraction uses, in order:

1. connector-native structured fields;
2. HTML metadata and JSON-LD;
3. semantic `time` elements;
4. conservative URL date patterns.

The row records `published_at`, `date_source`, and `date_confidence`. Unknown dates
remain unknown.

Each row receives `freshness_status`: `fresh`, `stale`, `undated`, or
`not_applicable`, plus `age_days` when calculable. Freshness does not replace content
validity or relevance. A profile or claim may require fresh evidence; stale evidence
remains observable but cannot support a current-state claim that declares a window.

Job rows additionally use `current_status`; closed, stale, search, landing, and
non-final pages cannot count as active openings.

## Extraction and Chunking — RB-011

Content extraction is content-type aware:

- HTML produces cleaned semantic blocks and preserves bounded table rows;
- long pages produce stable chunks instead of a single 4,000-character truncation;
- JSON and structured connector records retain useful fields;
- PDFs use an optional extractor adapter. The zero-dependency core may call an
  allowlisted local `pdftotext`; an optional Python PDF extra may be supported. When
  no extractor is available, the PDF remains an observable invalid row rather than
  decoded binary text.

Each chunk receives a stable `chunk_id`, parent evidence reference, content hash,
heading/context, and bounded text. Duplicate and claim logic operates on chunks while
retaining page-level provenance.

## Relevance and Diversity — RB-012

Relevance is separate from source quality. A deterministic BM25-lite/token-and-entity
score records:

- `relevance_score`;
- matched query/facet terms;
- title and body contributions;
- entity overlap;
- a bounded final rank combining relevance, quality, freshness, and source diversity.

Quality cannot rescue an irrelevant page, and relevance cannot rescue invalid content.
Facet coverage and relevant-yield are written to `facet_coverage.json`. Final previews
apply source-family diversity so one publisher or duplicated press release cannot fill
the evidence budget.

## Network Resilience and Etiquette — RB-013

Public fetches must use:

- an honest `research-engine/<version>` user agent;
- bounded exponential backoff with jitter;
- `Retry-After` when present and safe;
- per-host concurrency and delay limits;
- cached robots decisions with policy recorded per request;
- existing SSRF and redirect validation on every fetch.

Robots denial, rate limiting, and exhausted retries are explicit execution states, not
empty successful evidence.

## Bounded Repair — RB-009

After pass 1, repair runs only when a deterministic check fails:

- no executable sources -> enable the configured default public search;
- no relevant evidence -> simplify and broaden the failed facet query;
- freshness failure -> add current/as-of terms;
- source concentration -> request primary or independent sources;
- canonical refetch failure -> try the next bounded candidate URLs.

Only failed required facets are repaired. One repair pass is allowed. The engine
records pass-1 and pass-2 plans, execution, evidence provenance, failure reasons, and
a progress fingerprint. Identical yield/failure fingerprints stop with
`repair_no_progress`. Repair never relaxes validity, freshness, target, or security
gates.

## Independent Conflict Chains — RB-015

Each eligible row receives an `independence_key` derived from canonical publisher,
organization, repository, or explicit source-family metadata. Syndicated copies and
same-owner properties share a family when deterministically known.

Claim review records support and opposition chains separately. A high-confidence
claim requires the profile's minimum independent sources. Opposing claim-eligible
evidence from a distinct independence key produces `conflicted` or a lower confidence
ceiling. Search-query echoes, duplicate chunks, and the same row on both sides do not
form independent conflict chains.

M2 remains deterministic: profile-defined polarity terms and claim rules are allowed;
general LLM entailment is not required.

## Job-market Scope and Snapshot

Aggregate job analysis accepts an optional `research_scope.v1` document:

```json
{
  "schema_version": "research_scope.v1",
  "profile": "job_market",
  "as_of": "2026-07-16",
  "filters": {
    "geography": ["US"],
    "role_terms": ["AI Engineer", "Forward Deployed Engineer"],
    "levels": ["senior", "staff"],
    "companies": ["matrix"]
  }
}
```

Natural-language runs may use a profile's broad search facets, but quantitative job
market conclusions require an explicit scope. The Codex skill may translate user
intent into this scope; the core does not pretend to infer ambiguous geography or
level reliably.

`job_market_snapshot.json` records:

- requested and successfully checked companies/sources;
- active, closed, duplicate, rejected, and unknown-status counts;
- normalized company, role family/title, level, geography, skills, and published
  compensation when present;
- coverage denominator and failures;
- exact `as_of` and evidence IDs behind every aggregate.

Counts are observations within the stated coverage, not universal labor-market
estimates. Trend language is prohibited without a comparable prior snapshot.

## Artifacts

Existing artifacts remain backward compatible. M2 adds or extends:

- `query_plan.json`: profiles, facets, query IDs, provider and budgets;
- `collection_execution.json`: pass IDs, facet/query IDs, robots/backoff telemetry;
- `evidence.jsonl`: discovery lineage, chunking, date, freshness, relevance, and
  independence fields;
- `evidence_quality.json`: valid/relevant/fresh/independent counts;
- `facet_coverage.json`: required-facet yield and source diversity;
- `claim_review.json`: independent support/opposition chains and confidence ceilings;
- `repair_record.json`: trigger, changed queries, progress, and stop reason;
- `job_market_snapshot.json`: only for the aggregate job profile;
- `run_manifest.json`: M2 artifact contract and selected profile/provider.

Missing optional artifacts remain explicit in the manifest; they are never silently
invented.

## Failure and Safety Rules

- Discovery snippets never ground claims.
- A failed canonical fetch remains a failure row, not usable content.
- Search-provider, GitHub, ATS, robots, rate-limit, and extraction failures are
  sanitized and recorded.
- Query text is sent only to the selected provider disclosed in the plan.
- No connector bypasses login walls, paywalls, robots rules, platform controls, or
  account authorization.
- No account mutation, messaging, application submission, trading, or publishing is
  added.
- Optional credentials come only from environment/configuration and are never written
  to artifacts or the invocation journal.
- Thin or one-sided evidence ends in review-required or needs-more-evidence states.

## Evaluation and Acceptance

The versioned suite expands from the M0 validity fixture to B1-B10. Offline fixtures
are CI-gateable; live tests are explicit smoke tests and do not gate deterministic CI.

| Benchmark | Required M2 result |
| --- | --- |
| B1 fast market | stale evidence flagged against a 30-day window; no stale-only current claim |
| B2 technical comparison | canonical vLLM and SGLang repos plus per-project facets executed |
| B3 contested topic | distinct independent support/opposition chains lower the conclusion |
| B4 niche generic | JSON Canvas spec repo and adopters found without pack seeds |
| B5 GitHub survey | canonical projects in top 12 with license and maintenance fields |
| B6 adversarial | 5/5 invalid probes detected; zero invalid citations |
| B7 rerun | immutable distinct runs and coherent journal preserved |
| B8 mixed formats | tables preserved; PDF extracted or explicitly invalid; IDs unique |
| B9 market landscape | official vendor evidence covers company/product, pricing, demand, competition, and risk facets |
| B10 job market | scoped ATS fixture yields deduped active openings, coverage denominator, and no unsupported trend claim |

Additional acceptance gates:

1. every planned query is executed or has an explicit skip/failure reason;
2. every cited row is valid, claim-eligible, and sufficiently fresh when required;
3. discovery-only rows appear in lineage but never in claim citations;
4. one repair pass can improve a weak fixture and identical failure stops;
5. existing target-intelligence and M0 tests remain green;
6. full tests, Ruff, offline eval, generic live smoke, technical live smoke, and job
   live smoke pass or record an honest external limitation;
7. Fable performs a final independent review with no unresolved P0/P1 findings.

## Delivery Milestones

### M1 gate: autonomous discovery and executed planning

RB-005, RB-006, and RB-007 are complete. B2, B4, and B5 pass their deterministic
fixtures and live smoke where the external service is available.

### M2 gate: evidence intelligence and one-pass repair

RB-008, RB-009, RB-011, RB-012, RB-013, and RB-015 are complete. Market-landscape and
job-market profile acceptance tests pass. All B1-B10 offline gates pass and M0 remains
green.

## Non-goals

- LLM-based planning, synthesis, or entailment as a required runtime dependency.
- Multi-agent orchestration inside the engine.
- Unlimited crawling or exhaustive internet coverage.
- Paywall, login, CAPTCHA, robots, or platform-control bypass.
- Job application automation or account mutation.
- Labor-market population estimates from incomplete source coverage.
- Longitudinal diff, monitoring daemon, replay UI, embeddings, or vector storage.
- New domain packs beyond technical, market landscape, and job market in this batch.

## Loop Contract

**Goal:** Deliver the complete M1 and M2 capability described above without weakening
M0 trust guarantees or unrelated worktree changes.

**Input scope:** Current repository, approved M0 implementation, structured target
work, audit backlog RB-005 through RB-015, B1-B10 fixtures, and public read-only smoke
sources.

**Execute:** Implement in milestone order, test each boundary, run the milestone eval,
repair the shared boundary when a check fails, and record every review decision.

**Checks:** Focused unit tests, full tests, Ruff, diff check, offline B1-B10, bounded
live smokes, artifact schema assertions, privacy/redaction assertions, and independent
Fable review.

**Feedback:** A failed acceptance test maps to the responsible planner, connector,
extractor, quality, repair, or synthesis boundary. Do not patch benchmark-specific
output. External unavailability is recorded and does not justify weakening evidence
gates.

**Records:** Design, implementation plan, test/eval scorecards, smoke artifacts,
decision log, Fable findings, fixes, and final review report.

**Stop conditions:** Success requires the M2 gate and Fable approval. Stop and request
human direction if a fix requires destructive worktree operations, an undisclosed paid
service, account mutation, credentials in artifacts, or expansion beyond this scope.
