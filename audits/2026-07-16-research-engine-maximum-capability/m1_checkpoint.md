# M1 checkpoint

Date: 2026-07-16 (America/Los_Angeles)

Status: **passed**

## Deterministic gates

- Full suite: 207 passed.
- M0 evaluation: 9/9 checks passed; 5/5 invalid probes detected.
- Ruff: clean across `src` and `tests` (Ruff 0.15.22 installed under `/tmp` only).
- `git diff --check`: clean.
- Focused planning, discovery, GitHub, relevance, execution, and runner integration: 53 passed before the full-suite gate.

## M1 capability evidence

- Query plans are bounded, versioned as `query_plan.v2`, and reconcile every planned query to executed, failed, or explicitly skipped state.
- Web-search rows remain `discovery_only` and claim-ineligible; public candidates are deduplicated and canonically refetched through the existing SSRF-protected web connector.
- Execution telemetry preserves pass, facet, and query IDs and records bounded retry delays.
- Technical comparison planning emits per-project GitHub facets. A live quick smoke returned both `vllm-project/vllm` and `sgl-project/sglang` with license, archived, maintenance, raw-rank, and engine-rank fields.

## Live smoke notes

- Anonymous AnySearch returned `code=0` with the expected `data.results` envelope.
- Generic JSON Canvas smoke: complete, 20 rows, 3/3 planned queries executed, no warnings; the canonical specification was found without a seed URL.
- Technical vLLM versus SGLang smoke: complete, 20 rows, 3/3 per-project queries executed, no warnings; both canonical repositories ranked first for their project facets.
- One earlier diagnostic technical run observed an HTTP 429 during canonical GitHub-page refetch. The final per-project GitHub API smoke completed without that warning; the transient diagnostic is retained under `/tmp` and is not an acceptance failure.

## Compatibility and boundary decisions

- Programmatic `ResearchEngine.run` keeps `search_provider="none"` as a safe opt-out default for existing callers; CLI `research-engine run` defaults to anonymous AnySearch as required by the M2 design.
- Structured-target runs do not receive generic search fan-out.
- Explicit profile scopes override generic pack templates; matching explicit packs retain their legacy normalized templates.

