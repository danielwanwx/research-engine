# Research Engine

Pack-driven research orchestration for collecting evidence, preserving source traces, and producing deterministic synthesis artifacts.

This project is the standalone/open-source direction for the Research Engine. It is intentionally stdlib-first: packs are JSON files, connectors are small Python classes, and the runner writes transparent artifacts that an LLM can consume afterward.

## Quick Start

```bash
python -m research_engine.cli "research AI agent coding tools" --dry-run --output runs
python -m research_engine.cli "research DRAM HBM supply shortage" --output runs
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

## Artifact Output

Each run writes:

- `run_manifest.json`
- `query_plan.json`
- `evidence.jsonl`
- `claim_review.json`
- `supply_demand_matrix.json`
- `decision_brief.json`
- `research_report.md`

