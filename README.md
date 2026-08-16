# Research Engine

> Evidence-first research infrastructure for AI agents.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Research Engine is the evidence runtime behind an agent. It routes a question
to a research pack, runs bounded read-only connectors, normalizes and checks the
observations, and writes a concise conclusion with traceable evidence.

It is deliberately not a UI, a general multi-agent framework, or a long-report
generator. The default output is machine-readable so a Codex or other agent can
read the conclusion without loading thousands of unnecessary tokens.

## Quick start

Requires Python 3.10 or newer.

```bash
python -m pip install -e .
research-engine run "job descriptions" --pack auto --output runs
```

The default run writes `research_summary.json` and the supporting evidence
artifacts. Read the summary first. See [the artifact contract](docs/artifact-contract.md)
for the schema and failure semantics.

For development:

```bash
python -m pip install -e '.[dev,report]'
make check
make eval
```

## Explicit reports

Markdown and PDF are optional and are only generated when the user asks for a
report, article, or PDF:

```bash
python -m pip install -e '.[report]'
research-engine run "AI inference market" --report-mode full --output runs
```

The core install has no ReportLab dependency. Full mode without the `report`
extra exits with an installation hint. Summary mode always remains available.

Optional visible, user-consented browser recovery is a separate capability:

```bash
python -m pip install -e '.[browser]'
playwright install chromium
research-engine doctor browser
```

Install both optional capabilities with `.[all]`.

## Agent workflow

```text
question
  -> pack/profile routing
  -> query plan
  -> read-only connector collection
  -> normalized evidence and quality checks
  -> bounded repair
  -> research_summary.json
```

Typical commands:

```bash
# automatic routing; generic is the fallback
research-engine run "OpenAI company business model" --pack auto --output runs

# technical comparison
research-engine run "vLLM versus SGLang inference engines" \
  --pack technical --depth deep --output runs

# explicit quantitative job-market scope
research-engine run "AI engineer job market" --pack job_market \
  --scope-file scopes/ai-engineer-jobs.json --as-of 2026-08-15 --output runs

# authorized evidence exported from another tool
research-engine run "private customer research" \
  --external-evidence exports/customer.jsonl --output runs

# inspect local capability availability
research-engine doctor --format json
```

Use `--pack auto` for ordinary company, business, product, market, and job
description questions. Interview preparation requires explicit interview
intent; automatic routing does not inject interview queries into general
research.

## Artifacts

Each run is written to a unique directory such as
`runs/2026-08-15-job-descriptions/`:

```text
run_manifest.json          status, pack, report mode, warnings
research_summary.json      bounded agent-facing conclusion
query_plan.json            planned facets and queries
collection_execution.json  connector attempts and outcomes
evidence.jsonl             normalized source rows
chunks.jsonl               citation-ready content chunks
evidence_quality.json      quality, relevance, duplicates, conflicts
facet_coverage.json        required-facet coverage
claim_review.json          claim eligibility and confidence
decision_brief.json        deterministic decision synthesis
repair_record.json         bounded repair attempts and stop reason
loop_contract.json         loop policy
loop_record.json           loop outcome and feedback
```

Full mode additionally writes `research_report.md`, `research_report.pdf`, and
`pdf_report_status.json`. These are absent in summary mode.

Connector and research states remain separate. Each request record in
`collection_execution.json` uses the operational `status` field (`ok`,
`warning`, `failed`, `retry_exhausted`, `rate_limit`, `robots_denied`,
`timeout`, or `cache_hit`), a `row_count`, and, for classified transport
failures, an optional `failure_reason` such as `dns_resolution_failed`,
`network_timeout`, `network_unavailable`, or `tls_failure`.

This makes the important distinction explicit:

- a network failure has `status: failed` or `retry_exhausted` plus a
  `failure_reason` and usually `row_count: 0`;
- a successful zero-row request has an operational success status and
  `row_count: 0`;
- insufficient evidence is a claim-level outcome in `claim_review.json` (for
  example a claim `verdict` of `insufficient_evidence`), not a connector
  execution status;
- the run-level `failed_no_rows` status means no evidence rows were available
  after collection and repair.

An external failure is never treated as evidence that the researched phenomenon
does not exist. Inspect `collection_execution.json`, its `warnings`,
`status_counts`, `row_count`, and `failure_reason` fields before interpreting
an empty result.

## Packs and connectors

Packaged manifests in `src/research_engine/default_packs/` are the single source
of truth. Pass `--pack-dir` to overlay custom manifests. A pack can define
facets, query templates, source connectors, claim rules, and decision rules.

Built-in connector families include:

- `manual` and `external_jsonl` for controlled or authorized evidence;
- `web_search` and `web_page` for discovery and canonical refetch;
- `finance_quote` and `github_public_search` for public structured data;
- `official_job_discovery` for scoped careers/ATS collection;
- optional `authenticated_browser`, `agent_reach_bridge`, and `opencli_bridge`.

See [connector support](docs/connector-support.md) for access boundaries and
known limitations.

## Codex Skill

The repository includes a distributable Skill for natural-language research
requests:

```bash
mkdir -p ~/.codex/skills
cp -R skills/research-engine ~/.codex/skills/
```

The Skill runs the checkout's current source tree, defaults to summary mode,
reads `research_summary.json` first, and preserves the same pack-routing and
failure semantics as the CLI.

## Development layout

```text
src/research_engine/       runtime and connectors
tests/                     deterministic regression suite
evals/                     current offline benchmark fixtures
docs/                      user-facing contracts
examples/                  small agent integration examples
skills/research-engine/    Codex Skill
```

Keep new integrations behind the connector contract
`collect(CollectionRequest) -> CollectionResult`, keep acquisition read-only,
and add a deterministic fixture for each observed failure.

## License

MIT. See [LICENSE](LICENSE).
