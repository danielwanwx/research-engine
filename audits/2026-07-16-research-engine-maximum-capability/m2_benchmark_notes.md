# M2 B1-B10 benchmark notes

Date: 2026-07-16 (America/Los_Angeles)

The durable offline scorecard is at `m2-eval/scorecard.json` in this audit directory.
All evaluation inputs are local fixtures and all B1-B10 checks run without network
access.

| Gate | Result | Deterministic evidence |
| --- | --- | --- |
| B1 fast market | Pass | A dated row is stale at the 30-day boundary, remains observable, and is claim-ineligible. |
| B2 technical comparison | Pass | A fixture GitHub connector executes through the engine; vLLM and SGLang receive separate requests and collected repository artifacts. |
| B3 contested topic | Pass | Independent support and opposition chains produce `conflicted` with a medium ceiling. |
| B4 niche generic | Pass | Fixture discovery and canonical connectors execute through the engine, yielding the JSON Canvas spec, canonical repo, adopter page, and one bounded repair pass. |
| B5 GitHub survey | Pass | Canonical deep-research repositories rank in the top 12 with license and maintenance fields. |
| B6 adversarial | Pass | Nested M0 gate remains 9/9 and detects 5/5 invalid probes with zero invalid claim references. |
| B7 rerun | Pass | Two CLI runs reserve immutable directories and append distinct successful invocation-journal entries. |
| B8 mixed formats | Pass | HTML table, PDF adapter output, stable chunks, parent provenance, and unique IDs survive. |
| B9 market landscape | Pass | All seven fixture-connector facets execute through the engine and have relevant chunk yield plus definition/geography/as-of context. |
| B10 job market | Pass | Official active rows dedupe, outcome counts reconcile, coverage denominator is explicit, and no trend is inferred. |

## Live smoke evidence

- Anonymous AnySearch contract: available; returned the documented `code=0` and
  `data.results` envelope.
- Generic JSON Canvas: complete, 20 rows, 3/3 planned queries executed, no warnings.
- Technical vLLM versus SGLang: complete, 20 rows, both canonical repositories ranked
  first within their project facets with license and maintenance metadata.
- Market landscape: complete with warnings, 36 rows, 3/3 pass-1 queries executed,
  2/3 quick-depth facets covered, one bounded repair completed. Two canonical pages
  were honestly excluded by `robots_denied`; pricing remained a visible coverage gap.
- Scoped Anthropic job snapshot: complete, 5 official ATS rows observed, coverage 1/1
  checked, zero active rows. The snapshot explicitly rejected the returned candidates
  for role/level and, for two rows, geography mismatch; it emitted no trend claim.

Live results are diagnostic only. Search rank, public endpoint availability, robots
policy, and current job inventory are external state and do not alter offline
acceptance.
