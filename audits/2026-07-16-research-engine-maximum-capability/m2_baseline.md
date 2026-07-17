# M2 Implementation Baseline

## Recorded state

- Date: 2026-07-16
- Python: `/opt/homebrew/bin/python3.10`
- Unit tests: 160 passed
- Ruff: passed
- M0 offline evaluation: 9/9 checks; 5/5 invalid probes detected
- `git diff --check`: passed
- Worktree: intentionally dirty with approved M0 and structured-target changes plus
  audit/evaluation artifacts; no reset, checkout, clean, or wholesale commit is allowed.

## Compatibility contracts

- Invalid and discovery-only evidence cannot support claims, matrices, or conflicts.
- Run directories are immutable and atomically versioned.
- Evidence IDs are run-scoped and imported IDs remain in `source_evidence_id`.
- Opposing cited evidence calibrates stance and confidence.
- Parsed CLI runs append one redacted journal record before success output.
- `research_engine.v1` and `target_intelligence.v1` artifacts remain readable.
- Structured target claims require the complete company/role/level/geography contract
  and accepted final evidence; aggregate `job_market` work must not weaken that gate.

## Baseline dirty paths

The authoritative inventory is `git status --short` captured at phase start. Modified
core files include the Makefile, README, M0 design documents, artifact/CLI/web/loop/
quality/runner/security/synthesis modules, and their tests. Untracked baseline paths
include the audit directory, evaluation fixtures, target-intelligence modules and docs,
interview packs, and generated local output directories. M2 changes must preserve all
of them.
