# 07 — Capability Gap Matrix (Phase 4)

Ratings: strong | adequate | fragile | missing | intentionally_out_of_scope | unknown.
Every rating carries evidence refs (code file:line, benchmark, or run artifact) and confidence (H/M/L).
Machine-readable version: 07_gap_matrix.json.

| # | Dimension | Rating | Evidence | Conf |
|---|---|---|---|---|
| 1 | Intent clarification / question decomposition | **missing** | topic string passed verbatim; comparison intent lost (B2); wizard asks depth/scope not facets (interactive.py) | H |
| 2 | Pack routing / domain adaptation | **fragile** | routing works on match_terms (B1/B3→memory_cycle) but 1-word triggers misroute risk (packs.py:51 min_score=1); only 3 packs | H |
| 3 | Autonomous discovery / source registry | **missing** | B4: failed_no_sources with defaults, junk-only with all flags; no web search connector; no persistent source registry | H |
| 4 | Query generation/expansion/diversification/repair | **missing** | query_templates written to query_plan but never executed (packs.py:65, B2 notes); no expansion or repair | H |
| 5 | Web search / bounded crawl / sitemap / canonicalization | **missing** (search, crawl, sitemap) / adequate (URL canonicalization in dedupe, quality.py:186) | README:260 admits; B2/B4 | H |
| 6 | JS rendering / dynamic extraction | **fragile** | Playwright fallback works (B6 X page rendered) but silent on failure (web.py:182-185), no explicit renderer status in rows | H |
| 7 | PDF/table/structured/code/release/issue/dataset handling | **missing** | B6/B8: raw PDF bytes as text tier-high; tables flattened; no release/issue connectors | H |
| 8 | GitHub intelligence, license, maintenance | **fragile** | repo search works by exact name (Phase 3 probe); sort=updated noise (B5); no license/release/contributor fields (B5 row keys) | H |
| 9 | News/finance/filings/papers/patents/standards | **fragile** | finance_quote real-time but unofficial Yahoo endpoint, quotes only (B1); nothing else exists | H |
| 10 | Freshness window / as-of / temporal conflict / monitoring | **missing** | no published_at extraction (B1: all '-'); no windows; stale 3.5-month seeds presented as current (B1) | H |
| 11 | Authority/independence/source diversity | **missing** | source_confidence self-declared by pack (+0.15, quality.py:129); no domain reputation; no diversity metric; block pages 'high' (B6) | H |
| 12 | Relevance / reranking / evidence yield | **missing** | no relevance scoring at all — quality score is form-based; B5 noise ranked equally | H |
| 13 | Normalization/chunking/stable ID/canonical URL/content hash | **fragile** | normalization exists; **evidence_id collisions on external import** (B8); 4000-char truncation not chunking; content hash only in dedupe key | H |
| 14 | Semantic duplicate / source-family clustering | **missing** | exact URL/text-hash only (quality.py:174-189); no near-dup, no domain-family | H |
| 15 | Claim extraction / claim graph / citation entailment / coverage | **missing** | keyword-bucket counting (synthesis.py:179); B1: claims 'supported' by YouTube chrome; no entailment | H |
| 16 | Contradiction/uncertainty/confidence/abstention | **fragile** | conflict flags exist and fire (B3) but self-referential chains, confidence never adjusted (synthesis.py:33), no abstention | H |
| 17 | Retry/timeout/cache/backoff/rate-limit/budget/cancel | **fragile** | retry immediate no backoff (execution.py:136); soft timeout leaves threads; cache no TTL, date-keyed (B7); no budget/cancel | H |
| 18 | Repair loop / no-progress detection | **missing** | feedback_actions advisory only (loop.py:629); B2/B4 repairs were operator-driven | H |
| 19 | Persistent memory / incremental refresh / diff / monitor | **missing** | B7: no diff, cache same-day only; state.py = doctor capabilities only | H |
| 20 | Maker/checker & multi-agent isolation | **adequate** (within design) | checks are separate deterministic artifacts (loop.py); but checker can only warn, junk passes (B1) — no LLM/independent checker | M |
| 21 | Telemetry / replay / artifact schema / run comparison | **fragile** | per-request telemetry strong; **run-dir silent overwrite destroys history** (B4/B7); no replay tool, no run diff | H |
| 22 | Security/redaction/human gate/sandbox/supply chain | **strong** | SSRF guard (web.py:188), secret redaction (security.py), read-only posture, zero runtime deps, human gates documented; caveats: UA spoofing, no robots.txt (ethics/ToS exposure) | H |
| 23 | CLI/API/library UX & connector extensibility | **adequate** | clean small contract (base.py:14 lines); pack overlay dirs; but engine not installed → PYTHONPATH friction; flags required for any coverage | M |
| 24 | Benchmark/regression eval/adversarial/quality gate | **missing** | no eval harness in repo; tests 127 passing but all mocked (0.19s); README roadmap admits | H |
| 25 | Packaging/versioning/docs/contributor experience | **adequate** | pyproject clean, docs honest about limits (README:256-266); no CHANGELOG, no CI config visible, version 0.1.0 static | M |

## Summary counts
strong 1 · adequate 4 · fragile 8 · missing 12 · unknown 0.

## Notes on method
- Every "missing" is tied to a reproduced benchmark failure or a code location, not to competitor feature lists.
- Competitor-derived items appear only where a reproduced failure exists (03_primary_research_report.md mapping table).
- Dimension 22 rated strong on code evidence; the UA-spoof/robots point is a policy risk flag, not a code defect.
