# 09 — Prioritized Backlog (Phase 5)

Ranking = Impact × Frequency × Confidence ÷ (Effort × Risk). Full structured items: 08_backlog.jsonl.
Every item maps to a failure reproduced in this audit (benchmarks/*/notes.md) and names the benchmark that proves completion.

## P0 — correctness / systematic misleading (Milestone M0: Trust & Measurement Foundation)
| Rank | ID | Title | Proven by |
|---|---|---|---|
| 1 | RB-001 | Content validity gate (block/login/404/binary detection; http_status+content_type in schema) | B1, B6, B8 |
| 2 | RB-002 | Run-dir versioning — never silently overwrite | B4, B7 (two live incidents) |
| 3 | RB-003 | Evidence-ID uniqueness across sources | B8 |
| 4 | RB-004 | Claim-review integrity: validity-gated matching, conflict-aware confidence | B1, B3 |

## P1 — coverage / freshness / grounding (M0–M2)
| Rank | ID | Title | Milestone | Proven by |
|---|---|---|---|---|
| 5 | RB-010 | Benchmark & regression eval harness (commit B1–B8 as versioned suite) | M0 | all |
| 6 | RB-005 | Web-search connector (pluggable retriever; SearXNG key-free default) | M1 | B2, B4, B5 |
| 7 | RB-007 | GitHub intelligence: best-match ranking + license/release/maintenance fields | M1 | B5 |
| 8 | RB-006 | Execute decomposed queries (wire query_plan to collection; STORM-style facets) | M1 | B2 |
| 9 | RB-008 | Freshness: published_at extraction, as-of windows, staleness flags | M2 | B1 |
| 10 | RB-009 | Engine-executed bounded repair pass (1 pass, no-progress detection) | M2 | B2, B4 |

## P2 — depth / efficiency / observability (M2–M3)
RB-011 extraction upgrade (content-type, tables, PDF, chunking) · RB-012 relevance scoring/rerank · RB-013 backoff/rate-limit/robots/honest-UA · RB-014 cache TTL + `diff` command · RB-015 real conflict chains + confidence coupling

## P3 — specialization / long-term (M3–M4)
RB-016 near-dup/source-family clustering · RB-017 replay & run comparison · RB-018 pack expansion + validation (arXiv/EDGAR/RSS)

## Top 10 acceptance criteria
Each of ranks 1–10 carries concrete acceptance_tests in 08_backlog.jsonl; headline gates:
- RB-001: B6 rerun detects 5/5 adversarial probes; zero invalid rows cited by any claim.
- RB-002: same-command rerun produces a second run dir; originals immutable.
- RB-003: mixed-source run has zero duplicate evidence_ids (imported ids preserved in metadata).
- RB-004: B1 rerun cannot reach "supported/high" from platform-shell rows; B3 rerun caps confidence under conflict.
- RB-010: `make eval` runs offline fixture benchmarks and emits a scorecard; CI-gateable.
- RB-005: B4 rerun finds the JSON Canvas spec repo without any pack; B2 rerun contains vllm-project/vllm and sgl-project/sglang.
- RB-007: B5 rerun top-12 includes gpt-researcher/storm/open_deep_research with license fields.
- RB-006: executed search requests == planned queries in artifacts.
- RB-008: B1 rerun flags the 2026-03-31 TrendForce seed as stale for a 30-day window.
- RB-009: B4 recovers in ONE run with repair_pass recorded; repeated failure stops with explicit reason.

## Do Not Build Yet (hype-resistant list)
1. **Multi-agent orchestration** — Anthropic's own article prices it at ~15× tokens; the engine's differentiator is deterministic auditability beneath an LLM, not being one. Revisit post-M2.
2. **Embedded LLM synthesis/entailment** — until RB-010 can measure grounding, an LLM judge would be unfalsifiable. Design claim-entailment interface, don't ship.
3. **Embedding-based dedupe/rerank** — deps + nondeterminism; deterministic BM25-lite (RB-012) first.
4. **Vendoring Firecrawl or any AGPL code** — license-incompatible with MIT; external-service connector only.
5. **LangChain/LlamaIndex/Haystack dependency** — zero-dep core is a legitimate differentiator; keep integrations as optional extras.
6. **Monitoring daemon / scheduled refresh** — needs RB-014 cache semantics + RB-002 run versioning first (M3).
7. **More platform-search-page scraping** — B1/B2/B4 prove these produce block pages and JS shells; invest in RB-005 instead.
