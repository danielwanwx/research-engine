# Research Engine

Pack-driven research orchestration for collecting evidence, preserving source traces, and producing deterministic synthesis artifacts.

This project is the standalone/open-source direction for the Research Engine. It is intentionally stdlib-first: packs are JSON files, connectors are small Python classes, and the runner writes transparent artifacts that an LLM can consume afterward.

## Quick Start

Requires Python 3.10 or newer.

```bash
python -m pip install .
```

```bash
research-engine run "research AI agent coding tools" --pack auto --dry-run --output runs
research-engine run "research DRAM HBM supply shortage" --pack auto --output runs
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

## Data Source Limits

The built-in connectors use public endpoints and static page fetches. They do not bypass paywalls, login walls, robots controls, broker entitlements, or platform rate limits. A run may finish as `complete_with_warnings`, `failed_no_sources`, or `failed_no_rows`; inspect `run_manifest.json` before passing artifacts to an LLM.

## Concepts

- **Research packs**: topic profiles with match terms, query templates, source hints, claim specs, and matrix nodes.
- **Connectors**: source-specific collectors that return normalized evidence rows.
- **Runner**: chooses a pack, builds a query plan, runs connectors, writes artifacts.
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
- `web_page` for public page text extraction.
- `finance_quote` for public quote snapshots.

Additional platform integrations should live behind this same connector interface so the core runner remains source-agnostic.

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
- `evidence.jsonl`
- `evidence_quality.json`
- `claim_review.json`
- `supply_demand_matrix.json`
- `decision_brief.json`
- `research_report.md`

`run_manifest.json` includes `status`, connector warnings, and a compact quality summary. `evidence.jsonl` is the source trace an LLM should cite from, not a hidden intermediate; each row includes `quality_score`, `quality_tier`, duplicate metadata, and quality reasons. `evidence_quality.json` contains duplicate clusters, source-tier counts, and directional conflict flags that should be reviewed before final synthesis.

## Roadmap

- Add richer local-file/manual evidence import from CLI.
- Add optional logged-in browser collectors as external connectors, not core assumptions.
- Add an Agent Reach bridge as an optional upstream capability layer, not a runtime dependency: Agent Reach can discover/deep-crawl sources, then pass normalized rows into this engine for traceable artifact writing and deterministic synthesis.
- Add pack schema validation and examples for more domains.
- Expand quality scoring with source registries, citation graph checks, and pack-specific contradiction rules.
- Add async connector execution and retry/caching policies after the synchronous API is stable.
