# M2 general research usage

M2 adds unseeded generic, technical, market-landscape, and scoped job-market research
without changing the stricter structured-target contract.

## Search boundary

CLI runs default to anonymous `anysearch`. The exact provider and
`third_party_query_boundary` are written to `query_plan.json`. Disable web search with:

```bash
research-engine run "topic" --search-provider none
```

Use a self-managed search endpoint only by naming it:

```bash
research-engine run "topic" --search-provider searxng \
  --search-endpoint https://search.example.org/search
```

Search-result snippets remain `discovery_only` and `claim_eligible=false`. Public URLs
are deduplicated, checked against robots and SSRF policy, and canonically refetched.

## Scope files

Market scope:

```json
{
  "schema_version": "research_scope.v1",
  "profile": "market_landscape",
  "as_of": "2026-07-16",
  "filters": {
    "geography": ["US"],
    "definition": ["hosted AI inference platforms"]
  }
}
```

Job-market scope:

```json
{
  "schema_version": "research_scope.v1",
  "profile": "job_market",
  "as_of": "2026-07-16",
  "filters": {
    "role_terms": ["AI Engineer"],
    "levels": ["senior"],
    "companies": ["Anthropic", "OpenAI"]
  }
}
```

Job-market scope defaults to `geography: ["US"]` when geography is omitted. Job counts
still require non-empty role, level, and company filters. Quantitative scopes accept
multiple bounded companies, but `role_terms` and `levels` must each have exactly one
value; an explicitly supplied geography must also be singleton.
The plan records this axis policy plus any companies omitted by the selected depth
budget. `--as-of` overrides the scope date and is recorded in the manifest and plan.

## Freshness, extraction, and coverage

Publication, update, and latest-observation dates remain distinct. Publication dates use
connector-native fields, JSON-LD, HTML metadata, time elements, then conservative URL
dates; dated data-series tables can provide `observed_at`. Evidence is classified `fresh`, `stale`, `undated`,
`future_dated`, or `not_applicable` against each facet's window. When a facet requires
freshness, only `fresh` evidence can support its current claims; other rows remain
observable.

HTML headings, semantic blocks, and bounded tables are preserved. JSON remains
structured. Long content produces stable parent-linked chunks, and those chunks replace
the truncated parent preview during relevance, deduplication, conflict, and claim
synthesis. PDF succeeds only via an allowlisted local extractor; unavailable or failed
extraction is explicitly invalid.

`facet_coverage.json` reports relevant claim-eligible yield, missing required facets, and
required facets omitted by the selected query budget. Quality and relevance are
separate scores, and the report preview is source-diverse.

Full report mode converts the standard Markdown report to an A4 PDF with embedded CJK
fonts when available, clickable evidence links, page headers, footers, and page numbers.
It is an optional presentation of existing artifacts and does not run a second
synthesis pass. Summary mode does not import or require ReportLab.

## Repair and conflict limits

Failed required facets can trigger exactly one pass-2 repair. The engine may enable the
configured search path, simplify a query, add current/as-of terms, diversify source
terms, or try the next bounded canonical candidates. It never relaxes freshness,
validity, target, robots, or SSRF gates. `repair_record.json` records the trigger,
progress fingerprints, and `repair_completed`, `repair_no_progress`, or the explicit
reason no repair ran.

Claim chains count independent publisher/organization/repository families. Copies,
duplicates, query echoes, and self-conflict do not count twice. Distinct eligible
opposition caps confidence and produces a conflicted stance.
