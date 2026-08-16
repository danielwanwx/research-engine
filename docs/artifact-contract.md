# Artifact contract

Research Engine is an evidence runtime for agents. A normal run produces a
bounded conclusion first; it does not spend tokens rendering a long report.

## Default summary

```sh
research-engine run "job descriptions" --pack auto --output runs
```

The run directory contains `research_summary.json` plus the evidence and
quality artifacts needed to inspect the conclusion. Agents should read the
summary first and open the larger artifacts only when the question is
contested, incomplete, or explicitly asks for citations.

`research_summary.json` uses schema `research_summary.v1` and includes:

- `headline`: the concise conclusion;
- `stance`, `confidence`, and `action_bias`: decision-oriented labels;
- `rationale`: a bounded list of reasons;
- `quality_warnings` and `scope_warnings`: explicit uncertainty;
- `key_evidence`: at most ten citation-ready evidence references;
- `loop_status` and `stop_reason`: how collection ended.

The summary is intentionally bounded. Full source rows remain in
`evidence.jsonl`, while `evidence_quality.json`, `claim_review.json`,
`decision_brief.json`, and `loop_record.json` provide audit detail.

## Optional reports

Markdown and PDF are only produced when the user explicitly requests:

```sh
research-engine run "job descriptions" --report-mode full --output runs
```

Install the optional renderer first:

```sh
pip install "research-engine[report]"
```

Summary mode works with the core package alone. If full mode is requested
without the extra, the CLI exits with an actionable installation message and
does not reserve a partial run directory.

The manifest records `report_mode` and a `report` object. In summary mode the
report status is `not_requested`; in full mode it records Markdown and PDF
generation separately. A failed PDF never changes the research status.

## Connector outcomes

Transport state and research state are separate. Each request in
`collection_execution.json` records the operational `status`, `row_count`, and
an optional normalized `failure_reason`:

- operational statuses include `ok`, `warning`, `failed`, `retry_exhausted`,
  `rate_limit`, `robots_denied`, `timeout`, and `cache_hit`;
- transport failures are represented by `status: failed` or
  `status: retry_exhausted` plus a reason such as `dns_resolution_failed`,
  `network_timeout`, `network_unavailable`, or `tls_failure`;
- a successful zero-row response has an operational success status and
  `row_count: 0`;
- insufficient evidence is a claim-level result in `claim_review.json` (for
  example `claims[*].verdict: insufficient_evidence`), not a connector status;
- the run-level `failed_no_rows` status means no rows remained after collection
  and bounded repair.

For example, an AnySearch `URLError` is retried and produces
`status: retry_exhausted`, `failure_reason: dns_resolution_failed`, and
`row_count: 0`. It must not be described as a successful search with no rows.
No network failure is converted into evidence that the researched phenomenon
does not exist. Inspect `warnings`, `status_counts`, `row_count`, and
`failure_reason` before interpreting an empty result.

## Pack selection

`--pack auto` uses the packaged manifests in
`src/research_engine/default_packs/`. The generic pack is the fallback for
ordinary job descriptions, company or business research, products, and
markets. Interview preparation requires explicit interview intent. Custom
manifests can be supplied with `--pack-dir`; they overlay the packaged defaults
and are validated before planning.
