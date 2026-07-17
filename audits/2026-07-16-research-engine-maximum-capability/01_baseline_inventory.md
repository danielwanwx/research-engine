# 01 — Baseline Inventory (Phase 0)

As of 2026-07-16T13:12-07:00, repo `main@134662c` + uncommitted changes (see git_status_baseline.txt).
All statements below cite file:line in this worktree.

## Environment
- Python 3.14.3 (system homebrew); package NOT pip-installed — tests work via pytest `pythonpath=src`; CLI runs need `PYTHONPATH=src`. Doctor: 4/11 capabilities (python, research_engine, `gh`, `playwright`); missing: agent-reach, twitter, rdt, xhs, xq, yt-dlp, opencli. No `GROK_API_KEY`/`XAI_API_KEY` set. `ruff` not importable (dev extra not installed) — lint unrunnable as-is; recorded, not fixed.
- Tests: **127 passed in 0.19s** (pytest_output.txt). 0.19s total ⇒ entire suite is offline/mocked; no live-network integration or E2E test exists.
- No AGENTS.md/CLAUDE.md anywhere in repo.

## What the engine is (FACT)
A single-pass, deterministic evidence-collection pipeline: pack routing → source plan → concurrent read-only connectors → normalization → heuristic quality/dup/conflict checks → keyword claim review → artifact bundle (11 files per run) → stop with explicit reason. ~6.2k LOC, zero runtime dependencies (stdlib only; Playwright optional).

## Capability classification

### Implemented and solid (given its scope)
1. **Artifact traceability** — every run writes run_manifest, query_plan, collection_execution (per-request status/attempts/cache/elapsed_ms), evidence.jsonl, evidence_quality, claim_review, supply_demand_matrix, decision_brief, loop_contract, loop_record, research_report.md (runner.py:324–345).
2. **Explicit stop reasons** — planned/no_executable_sources/sources_returned_no_evidence/critical_check_failed:*/completed_with_review_required/acceptance_checks_passed (loop.py:689–704).
3. **Safety/redaction** — SSRF guard with public-IP resolution + redirect validation (web.py:188–219); sensitive-key/value redaction incl. cookies/tokens/bearer/URL params (security.py); external-path hashing; loop-level sensitive-field check (loop.py:733).
4. **Bounded execution** — ThreadPool ≤ max_workers, retries, optional soft timeout, per-source result caps, optional file cache with telemetry (execution.py).
5. **Graceful degradation of optional bridges** — missing CLIs/keys warn, don't crash (xai_discovery.py:30–38; doctor).

### Implemented but fragile
6. **Web collection** — explicit seed URLs only; stdlib fetch + HTMLParser text (no boilerplate removal); bot-gate heuristic 4 substrings (web.py:132–140); Playwright fallback swallows all exceptions silently (web.py:182–185 `except Exception: return "", ""`); **evidence truncated to 4000 chars** (web.py:93); no robots.txt check; no per-host rate limiting; UA spoofs Chrome.
7. **Quality scoring** — base 0.5 ± heuristics; `source_confidence` is pack/self-declared and worth ±0.15–0.2 (quality.py:104–154) ⇒ circular authority; no domain reputation, no independence measure.
8. **Duplicate detection** — exact canonical-URL or sha1(title|text[:240]) only (quality.py:174–189); no near-dup/semantic/source-family clustering.
9. **Conflict detection** — 2 hardcoded directional term sets, substring co-occurrence (quality.py:26–37); no numeric/temporal/claim-level conflicts.
10. **Claim review** — keyword-bucket counting against pack claim_specs (synthesis.py:179–195); "supported" = N docs contain a keyword; no citation entailment, no span-level grounding.
11. **Retry** — immediate re-call, no backoff/jitter/rate-limit awareness (execution.py:136–168); timeout leaves threads running (soft only).
12. **Cache** — no TTL/expiry; key includes run_date so daily reruns never hit cache across days; disabled by default (execution.py:228–268).

### Documented/roadmapped but NOT implemented (README:284–294 confirms)
13. Crawler (bounded/sitemap), broad autonomous discovery, query repair passes, persistent loop memory, citation-graph checks, benchmarks/evals, source registries.
14. **Repair loop absent in code**: feedback_rules/feedback_actions are advisory strings written into artifacts (loop.py:191–246, 629–664); nothing re-executes. README "loop-first execution" is single-pass + post-hoc checks.
15. **query_templates are not executed**: build_pack_queries fills query_plan.json (packs.py:65–76) but no connector consumes those queries (web/finance/manual take pack config directly; github/platform-pages derive from platform plan). Planned queries ≠ collection.

### Key structural facts for benchmarks
- Depth caps: quick=3, deep=8, audit=12 rows/source (runner.py:66).
- Generic pack: `sources: []` ⇒ topic without matching pack and without flags → `failed_no_sources` (runner.py:216, 691).
- Discovery options: pack seeds; `--web-search-pages` (≤6 public platform search pages: HN/Reddit/GitHub/YouTube); `--platform-scope all` (adds github_public_search); structured target (`--target-*`) → official_job_discovery + xai_discovery (needs API key) + conditional refetch — the ONLY multi-step retrieval in the codebase (runner.py:235–253).
- 3 packs only: generic, memory_cycle (DRAM/HBM; hardcoded TrendForce/Micron 2026 URLs), interview_prep.
- Pack routing: substring match-term counting; min_match_score default 1 ⇒ one word like "hiring" routes to interview_prep (packs.py:79–95).
- Freshness: no freshness window/as-of enforcement anywhere; captured_at always recorded; published_at only from X snowflake or pack metadata.
- finance_quote: unofficial Yahoo v8 chart endpoint, price+52wk range only (finance.py:57–61).
- github_public_search: unauthenticated repo search; stars/forks/language/topics; **no license/release/contributor/issue data** (github_public.py:104–126).

## Test/dossier detail → test_and_doctor_results.md, architecture_inventory.json
