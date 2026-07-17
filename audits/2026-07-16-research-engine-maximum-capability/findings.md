# Findings — working notes (primary researcher)

## Phase 0 code inventory (as of 2026-07-16, commit 134662c + dirty worktree)

### Architecture facts (FACT, from code)
- **Entry points**: `research` (interactive wizard), `research-engine run|doctor` (cli.py). Bare topic auto-inserts `run`.
- **Depth caps** (runner.py:66): quick=3, deep=8, audit=12 max_results per source. No token/cost budget concept.
- **Connector set** (runner.py:54): manual, external_jsonl, web_page, finance_quote, github_public_search, official_job_discovery, xai_discovery, agent_reach_bridge, opencli_bridge. **No general web-search connector** — discovery relies on: pack seed `web_pages`, `--web-search-pages` (fetch platform search result HTML pages for hackernews/reddit/github/youtube, ≤6), `--platform-scope all` (adds github_public_search), structured-target xai_discovery, or external JSONL.
- **Single-pass execution**: runner.run() collects once; the only conditional second pass is target_discovery_refetch (structured targets, refetches xai-discovered URLs). No repair loop, no query re-expansion, no iterative retrieval.
- **Packs** (packs.py): overlay of package default_packs + ./packs. Routing = count of match_terms substring hits, ties by pack order. generic pack has `sources: []` → generic-topic run without flags = 0 executable sources → `failed_no_sources`. Only 3 packs: generic, memory_cycle (DRAM/HBM finance, hardcoded 2026 seed URLs), interview_prep.
- **query_templates are cosmetic for collection**: build_pack_queries writes queries into query_plan.json, but no connector consumes them except platform search pages/github query derived from platform plan. Queries ≠ collection requests.
- **Execution layer** (execution.py): ThreadPool ≤4 workers; retries default 1 (immediate, no backoff, no jitter, no rate-limit awareness); optional per-source soft timeout enforced at future.result() (thread keeps running; executor shutdown cancel_futures on timeout); file cache keyed by sha256(connector+source+topic+run_date+depth+max_results) — no TTL/expiry, cache disabled by default.
- **web_page connector** (connectors/web.py): explicit seed URLs only; stdlib urllib fetch, UA-spoof Chrome; SSRF guard (public-IP resolution, scheme/credential checks, redirect validation); 2MB body cap; HTMLParser text extraction (no readability/boilerplate removal); bot-gate heuristics ("enable javascript" etc.); Playwright optional silent fallback; **evidence text truncated to 4000 chars**; no robots.txt check; no rate limiting per host; no HTTP caching headers.
- **github_public_search**: unauthenticated api.github.com repo search, sort=updated, per_page ≤20, captures stars/forks/language/topics. No license, no release, no contributor, no issue data.
- **quality.py**: deterministic heuristic scoring (base 0.5 ± connector class, confidence label, https, title, text≥240 chars). Note: source_confidence comes from pack metadata (self-declared). Dedupe = exact canonical URL or sha1(title|text240) — no semantic/near-dup. Conflict = 2 hardcoded directional term sets (or pack quality_rules) via substring co-occurrence — no claim-level or numeric conflict detection.
- **loop.py**: 13 checks, all post-hoc on one pass; feedback_actions are advisory strings written to loop_record.json — engine never acts on them. stop_reason vocabulary good. QUALITY_PASS_THRESHOLD 0.55 only warns.
- **Freshness**: no freshness window concept anywhere; captured_at recorded; published_at only from x.com snowflake IDs or page metadata provided by pack; no stale detection.
- **Citation/claim grounding** (synthesis.py — to verify): claim_specs keyword matching per pack.

### Immediate capability implications (INFERENCE)
- Autonomous discovery for arbitrary topics is near-absent: without a pack or flags, run fails with no sources. With --web-search-pages, gets platform search HTML pages (Google search page itself not included; only HN/Reddit/GitHub/YouTube search pages), which are JS-heavy/bot-gated in practice.
- Evidence depth capped: 4000 chars/page, ≤3–12 rows/source.
- No repair/iteration: feedback rules documented but not executed.
- Reproducibility good (artifacts complete), but no replay tooling.

### To verify next
- synthesis.py claim review; doctor.py capability report; xai_discovery (does it need API key? — likely calls xAI API), finance connector endpoint; targets.py; security.py redaction; tests pass/fail.
