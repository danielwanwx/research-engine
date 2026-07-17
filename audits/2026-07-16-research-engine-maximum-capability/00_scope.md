# Research Engine Maximum-Capability Audit — Scope

- **Date:** 2026-07-16 (America/Los_Angeles, UTC-7)
- **Repository:** /Users/danielwan/Project/research-engine
- **Branch:** main @ 134662c87d8d1d50f0a3e1b43dbbc6ce29cd6d72 (dirty worktree — see git_status_baseline.txt)
- **Auditor:** Fable5 (primary researcher) + research_observer (independent subagent)
- **Mode:** Audit-only. No modification to source, tests, config, deps, docs, git state, or user's uncommitted changes.
- **Write scope:** only `audits/2026-07-16-research-engine-maximum-capability/` (this directory).

## Goals
1. Establish what the Research Engine can actually do today (evidence: code, tests, real runs).
2. Identify where it loses coverage, freshness, accuracy, traceability, efficiency, reliability.
3. Survey strongest public research-agent / retrieval / citation / eval systems for transferable methods.
4. Produce a prioritized, evidence-backed backlog with acceptance tests.

## Rules in force
- Read-only external sources only; no logins, no paywall/robots bypass, no credential handling.
- No dependency installation without user approval.
- External Fallback (evidence gathered outside the engine) must be labeled and traced to the engine capability gap that forced it.
- Failures, empty results, stale data, and conflicts are evidence — recorded, not hidden.
- Observer isolation: no research-quality feedback exchanged before both reports are sealed.
- One subagent only: research_observer.

## Planned phases
- Phase 0: baseline inventory (this doc, run_manifest, code/test/doctor audit)
- Phase 1: design 6–8 benchmarks before running any
- Phase 2: execute benchmarks through the engine's real workflow
- Phase 3: self-hosting test — use the engine to research the deep-research ecosystem
- Phase 4: 25-dimension capability gap scan
- Phase 5: prioritized backlog
- Phase 6: sealed reconciliation with observer, final report
