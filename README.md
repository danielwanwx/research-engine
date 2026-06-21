# Research Engine

Pack-driven research orchestration for collecting evidence, preserving source traces, and producing deterministic synthesis artifacts.

This project is the standalone/open-source direction for the Research Engine. It is intentionally stdlib-first: packs are JSON files, connectors are small Python classes, and the runner writes transparent artifacts that an LLM can consume afterward.

## Quick Start

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

## Concepts

- **Research packs**: topic profiles with match terms, query templates, source hints, claim specs, and matrix nodes.
- **Connectors**: source-specific collectors that return normalized evidence rows.
- **Runner**: chooses a pack, builds a query plan, runs connectors, writes artifacts.
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

## Artifact Output

Each run writes:

- `run_manifest.json`
- `query_plan.json`
- `evidence.jsonl`
- `claim_review.json`
- `supply_demand_matrix.json`
- `decision_brief.json`
- `research_report.md`

## Roadmap

- Add richer local-file/manual evidence import from CLI.
- Add optional logged-in browser collectors as external connectors, not core assumptions.
- Add an Agent Reach bridge as an upstream capability layer: Agent Reach can discover/deep-crawl sources, then pass normalized rows into this engine for traceable artifact writing and deterministic synthesis.
- Add pack schema validation and examples for more domains.
- Add async connector execution and retry/caching policies after the synchronous API is stable.
