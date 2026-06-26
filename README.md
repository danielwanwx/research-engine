# Research Engine

Evidence-first research loops for AI agents.

Research Engine turns heterogeneous evidence from web pages, browser sessions, CLI tools, APIs, and manual captures into auditable research artifacts that agents and LLMs can analyze, verify, and improve over time.

It is intentionally stdlib-first: packs are JSON files, connectors are small Python classes, and the runner writes transparent artifacts before an LLM consumes anything.

## What Makes It Different

Research Engine is not just another crawler.

- **AgentReach** installs and exposes upstream platform CLIs.
- **OpenCLI** turns websites and browser workflows into CLI-accessible capabilities.
- **Research Engine** orchestrates research intent, evidence normalization, source quality scoring, contradiction checks, synthesis artifacts, and loop memory.

AgentReach and OpenCLI are useful upstream capability providers. They should feed Research Engine; they are not required runtime dependencies for the core package.

## Quick Start

Requires Python 3.10 or newer.

```bash
python -m pip install -e '.[dev]'
```

```bash
research-engine run "research AI agent coding tools" --pack auto --dry-run --output runs
research-engine run "research DRAM HBM supply shortage" --pack auto --output runs
research-engine run "research DRAM HBM supply shortage" --pack auto --output runs --max-workers 4 --retries 1
research-engine run "research Lenny memory discussion" --external-evidence exports/lenny.jsonl --output runs
```

The module entrypoint works the same way:

```bash
python -m research_engine.cli run "research AI agent coding tools" --pack auto --dry-run
```

For local development:

```bash
python -m pytest -q
python -m ruff check src tests
```

Or use the Makefile:

```bash
make test
make lint
make check
```

Check optional local capabilities:

```bash
research-engine doctor
research-engine doctor agentreach
research-engine doctor opencli --format json
```

## Data Source Limits

The built-in connectors use public endpoints and static page fetches. They do not bypass paywalls, login walls, robots controls, broker entitlements, or platform rate limits. A run may finish as `complete_with_warnings`, `failed_no_sources`, or `failed_no_rows`; inspect `run_manifest.json` before passing artifacts to an LLM.

## Concepts

- **Research packs**: topic profiles with match terms, query templates, source hints, claim specs, and matrix nodes.
- **Connectors**: source-specific collectors that return normalized evidence rows.
- **Execution**: runs connector requests with bounded concurrency, retry telemetry, and optional result caching.
- **Runner**: chooses a pack, builds a query plan, delegates collection to the execution layer, writes artifacts.
- **Evidence quality**: deterministic source scoring, duplicate detection, and directional conflict flags written before synthesis.
- **Synthesis**: deterministic scoring over collected evidence; LLM analysis happens after the traceable evidence pack exists.

## Pack Model

Packs are JSON files. A pack can define:

- `match_terms` for automatic topic routing.
- `query_templates` for collection planning.
- `finance_tickers`, `web_pages`, or custom `sources`.
- `claim_specs` and `matrix_nodes` for deterministic synthesis.
- `decision_rules` for stance summaries and action-bias labels.

The runner uses the highest-scoring pack unless `--pack <id>` is supplied. Use `--pack auto` for explicit automatic selection.

## Connector Model

Connectors implement a small `collect(CollectionRequest) -> CollectionResult` interface. The scaffold includes:

- `manual` for local or pack-provided rows.
- `external_jsonl` for authorized evidence exported by logged-in browser tools, Agent Reach, or proprietary collectors.
- `web_page` for public page text extraction.
- `finance_quote` for public quote snapshots.
- `agent_reach_bridge` for optional AgentReach/upstream CLI results.
- `opencli_bridge` for optional OpenCLI read-only adapter output.

Additional platform integrations should live behind this same connector interface so the core runner remains source-agnostic.

See `docs/connector-support.md` for the current support matrix and planned connectors.

OpenCLI bridge sources are pack-driven in v1. Example:

```json
{
  "source_id": "opencli_x_seed",
  "connector": "opencli_bridge",
  "platform": "x",
  "query": "loop engineering",
  "command": "opencli x search --query \"{query}\" --limit {max_results} --format json"
}
```

Minimal connector example:

```python
from research_engine.models import CollectionResult


class MyConnector:
    connector_id = "my_source"

    def collect(self, request):
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=[{"title": "Example", "url": "https://example.com", "text": "Evidence"}],
        )
```

## Artifact Output

Each run writes:

- `run_manifest.json`
- `query_plan.json`
- `collection_execution.json`
- `evidence.jsonl`
- `evidence_quality.json`
- `claim_review.json`
- `supply_demand_matrix.json`
- `decision_brief.json`
- `research_report.md`

`run_manifest.json` includes `status`, connector warnings, execution summary, and a compact quality summary. `collection_execution.json` records request-level connector status, attempts, cache hits, row counts, and warnings. `evidence.jsonl` is the source trace an LLM should cite from, not a hidden intermediate; each row includes `quality_score`, `quality_tier`, duplicate metadata, and quality reasons. `evidence_quality.json` contains duplicate clusters, source-tier counts, and directional conflict flags that should be reviewed before final synthesis.

Connector result caching is opt-in via `--cache-dir`; leave it off when source freshness matters.

## External Evidence

Use `--external-evidence path.jsonl` when evidence comes from a logged-in browser session or another authorized collector. Each JSONL line should be an object with at least:

```json
{"title": "Source title", "url": "https://example.com", "text": "Visible evidence text", "metadata": {"platform": "lenny"}}
```

The engine imports these rows through the same execution, quality, and synthesis pipeline as built-in connectors. It does not read cookies, bypass login walls, or control Chrome.
Artifact references store only the evidence filename plus a stable path hash; full local paths, cookies, authorization headers, and token-like fields are redacted or dropped before rows are written.
Optional CLI bridges execute without a shell, enforce allowlisted entrypoints, and reject command terms or flags associated with account mutation or child-command execution.

## Roadmap

- Add richer local-file/manual evidence import from CLI.
- Add optional logged-in browser collectors as external connectors, not core assumptions.
- Expand the AgentReach bridge as an optional upstream capability layer, not a runtime dependency.
- Expand the OpenCLI bridge for authorized read-only adapters and no-API websites.
- Add a deeper web crawler connector for sitemap, bounded crawl, and optional Playwright rendering.
- Add loop runtime, reflection, persistent memory, and deterministic evals.
- Add pack schema validation and examples for more domains.
- Expand quality scoring with source registries, citation graph checks, and pack-specific contradiction rules.
- Add async connector execution and retry/caching policies after the synchronous API is stable.
