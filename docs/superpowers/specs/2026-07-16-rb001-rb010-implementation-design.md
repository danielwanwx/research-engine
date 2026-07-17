# RB-001 and RB-010 Implementation Design

## Scope

Implement the first approved optimization batch from the maximum-capability audit:

- RB-001: content validity gate for fetched evidence.
- RB-010: minimal offline regression evaluation harness.

Do not implement discovery, repair loops, freshness, run versioning, evidence-ID changes, or embedded LLM judging in this batch.

## Existing constraints

- The worktree already contains user changes in web collection, target intelligence, quality, runner, and tests. Preserve them and patch only the shared paths required by RB-001/RB-010.
- Keep the zero-runtime-dependency core.
- Preserve the public fetch_text and fetch_page return shapes.
- Invalid content remains visible as evidence rows for observability, but it must never support claims.

## RB-001 design

Add a small immutable FetchedPage result in the web connector containing:

- text
- final_url
- http_status
- content_type
- content_valid
- content_invalid_reasons

The web connector records these fields on every returned row and emits a warning for invalid content. HTTP errors, unsupported binary content, empty/short shells, and known login/block/captcha pages are invalid. HTML, plain text, JSON, and XML remain supported. PDF is quarantined until the separate extraction backlog is implemented.

Quality scoring applies a shared deterministic eligibility check. Invalid rows receive quality score 0, tier low, an invalid-content reason, and run-level warning/count metadata.

Synthesis filters documents through the same eligibility check. Pack claims, generic claims, and matrix nodes therefore cannot cite invalid evidence.

Structured-target claims use the same eligibility gate. Browser-rendered invalid
content cannot replace a valid static response, and short non-web evidence is not
subjected to the web-shell length rule.

Compatibility:

- fetch_text still returns str.
- fetch_page still returns tuple[str, str].
- both wrappers return empty content for invalid pages.
- fetch_page_result exposes full metadata to WebPageConnector.

## RB-010 design

Add a dependency-free offline eval command implemented as a Python module and exposed through make eval.

The first fixed corpus targets the exact RB-001 failure:

- valid HTML
- login wall
- network-security block page
- HTTP 404 body
- raw PDF bytes
- simulated DNS/transport failure

The eval uses deterministic fake transport responses through the real web connector;
it performs no network access. It writes a JSON scorecard under a caller-supplied
output directory and exits nonzero unless:

- all four invalid probes are detected;
- valid HTML remains eligible;
- no invalid evidence ID appears in claim or matrix output;
- invalid evidence is excluded from generic claims, pack claims, structured-target
  claims, matrices, and conflict flags;
- invalid rows stay present for observability.

This is the M0 seed, not a general benchmark framework. New benchmark cases can be added only when another backlog item requires a measurable regression.

## Files

Expected changes are limited to:

- src/research_engine/connectors/web.py
- src/research_engine/quality.py
- src/research_engine/synthesis.py
- src/research_engine/eval.py
- tests/test_connectors.py
- tests/test_quality.py
- tests/test_synthesis.py
- tests/test_eval.py
- Makefile
- README.md only for the new eval command

## Checks

- Existing test suite passes under Python 3.10+.
- New unit tests cover each invalid-content class.
- make eval emits a passing JSON scorecard.
- Ruff passes.
- Git diff confirms no unrelated user change was overwritten.

## Stop conditions

Success: tests, eval, and lint pass; independent Fable review has no unresolved correctness finding.

Stop and report: the implementation requires a new dependency, a destructive rewrite of existing user changes, or acceptance cannot be met without expanding beyond RB-001/RB-010.
