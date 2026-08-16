# Agent-First Repository Convergence Design

**Date:** 2026-08-15  
**Status:** Approved for planning  
**Scope:** `research-engine` only; LoopCoach is explicitly out of scope.

## Objective

Refocus Research Engine as a compact evidence runtime for Codex and other AI agents. The default contract is a machine-readable conclusion with evidence and explicit failure semantics, not a long-form report. Preserve valuable connector and evidence-governance behavior while removing generated history, duplicate configuration, stale documentation, and unnecessary default dependencies.

## Product Boundary

Research Engine owns this pipeline:

1. select a pack/profile and form a query plan;
2. execute connectors and normalize their observations;
3. distinguish transport/authentication failures from successful zero-row results;
4. evaluate relevance, evidence quality, and scope;
5. run bounded repair when evidence is insufficient;
6. persist a stable machine-readable summary and audit artifacts.

It does not own a user interface, a general multi-agent framework, or long-form publishing by default. Markdown and PDF reporting remain an explicit `full` mode for users who request an article-like artifact.

## Public Contract

The primary command remains:

```sh
research-engine run "<question>" --output <directory>
```

Summary mode remains the default. Its primary artifact is `research_summary.json`, containing the conclusion, rationale, warnings, bounded key evidence, and loop outcome. The run manifest records the requested report mode and the status of optional report artifacts.

Connector outcomes remain separate from research conclusions:

- `failed_network`: the remote service could not be reached after bounded retry;
- `failed_auth`: credentials or login state prevented collection;
- `succeeded_no_rows`: the connector completed successfully and returned no observations;
- `insufficient_evidence`: collection ran, but the resulting evidence cannot support a conclusion.

No connector failure may be represented as evidence that the researched phenomenon does not exist.

## Repository Shape

The public repository should retain only current product code, tests, compact user documentation, current evaluations, the distributable Skill, and packaging/CI metadata.

### Remove

- `audits/2026-07-16-research-engine-maximum-capability/`: a 319-file historical run snapshot. Preserve only any still-relevant benchmark assertions in the current eval suite.
- `output/pdf/`: generated output that should never be a tracked source artifact.
- root `packs/`: six byte-identical copies of `src/research_engine/default_packs/`. Packaged defaults become the single source of truth; `--pack-dir` remains the custom override.
- superseded implementation-history documents under `docs/superpowers/` after extracting current contracts into user-facing documentation.

User-owned, untracked directories (`evidence_exports/`, `monitor-runs/`, `outputs/`, `reports/`, `scripts/`, and `work/`) are not part of this cleanup and must not be deleted or committed.

### Consolidate

- Merge `evals/v1` and `evals/v2` into one current evaluation layout. Retain every fixture still referenced by the active benchmark.
- Replace overlapping M2/report/target documentation with current `artifact-contract.md`, architecture, and connector-support documentation.
- Rewrite the README around the agent-first path: install, one command, artifact contract, failure semantics, custom packs, and links to detailed docs.

### Add

- a minimal GitHub Actions workflow for supported Python versions, tests, and Ruff;
- `docs/artifact-contract.md`;
- a small `examples/agent_usage.py` that consumes `research_summary.json` without depending on report rendering;
- a packaging smoke test proving summary mode works without ReportLab.

## Dependency Design

The core runtime should not require ReportLab. Move it to a `report` optional dependency group. Keep Playwright in the existing browser extra, and provide an `all` extra for users who want both optional capabilities.

Requesting `--report-mode full` without the report extra must fail with a concise installation instruction. Summary mode must neither import nor require ReportLab.

## Module Boundaries

Keep `ResearchEngine.run()` as the stable public seam. Reduce `runner.py` by moving cohesive internal phases behind a small number of deep modules:

- collection pipeline: connector dispatch, observations, and source-attempt outcomes;
- evaluation pipeline: relevance, quality, scope, claim eligibility, and bounded repair;
- artifact transaction: summary, manifest, evidence, and optional full report persistence.

Existing specialized connectors remain available; this change does not rewrite or delete working integrations merely to reduce file count. Avoid introducing framework-style interfaces or dependency injection that do not remove concrete complexity.

## Pack and Skill Contract

Packaged manifests in `src/research_engine/default_packs/` are authoritative. Tests must validate those manifests directly rather than enforce a second root copy. The generic pack remains the fallback for ordinary job descriptions, companies, products, businesses, and markets; interview preparation requires explicit interview intent.

The repository Skill and installed Skill must describe the current CLI, default summary mode, artifact selection, pack routing, and failure semantics. Skill synchronization is performed only after code and tests are current.

## Verification

The implementation is complete only when:

1. the full Python test suite passes;
2. Ruff passes for source and tests;
3. package build/install smoke tests pass with core dependencies only;
4. summary mode succeeds without ReportLab;
5. full mode either produces its report or gives the documented missing-extra error;
6. generic and interview-routing regression tests pass;
7. network failure and successful zero-row fixtures remain distinguishable;
8. `git diff --check` is clean;
9. LoopCoach has no modifications;
10. the final commit contains none of the user's untracked run/output directories.

## Delivery Strategy

Implement in reviewable stages: first repository and documentation consolidation, then optional dependency packaging, then runner boundary extraction, followed by Skill synchronization and complete verification. Deletions happen only after referenced fixtures and current contracts have been migrated. The final change is committed and pushed to the repository's existing branch after review.

