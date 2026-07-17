# B1 — Fast-moving market research (DRAM/HBM pricing)

- Command: `PYTHONPATH=src python3 -m research_engine.cli run "DRAM HBM memory contract price supply July 2026" --pack auto --depth deep --platform-scope all --web-search-pages --source-timeout-seconds 30 --output runs`
- Executed: 2026-07-16 ~13:25-07:00, wall clock 12.7s
- Run dir: `runs/2026-07-16-dram-hbm-memory-contract-price-supply-july-2026`
- Result: status=complete, 10 rows, loop=complete_with_review_required, 0 warnings
- No repair pass needed (rows returned). No external fallback used.

## Planned vs executed vs returned
- Planned 4 sources (finance watchlist, web seeds, github_public_search, platform_search_pages); all executed "ok".
- github_public_search: **status "ok", 0 rows, no warning** — full 8-word topic string sent verbatim to GitHub repo search; predictable zero; no query simplification; empty result invisible in run status (misleading-success pattern).

## Evidence findings (evidence.jsonl)
- finance_quote (4 rows): real-time prices present (MU 853.2 USD etc.) — genuine freshness win. But text is one line; no history/volume; unofficial Yahoo endpoint.
- Seed pages (2 rows): TrendForce 2026-03-31 press release + Micron FQ2-26 results — **3.5 months stale for a "July 2026" question, no published_at extracted anywhere, no staleness flag**. Both truncated to exactly 4000 chars.
- Platform search pages (4 rows):
  - Reddit → **network-security block page counted as evidence** (`"You've been blocked by network security..."`, 143 chars), `access_blocked: False` because text is non-empty.
  - HN Algolia → JS shell, "0 results" text captured as evidence.
  - YouTube → 4000 chars of homepage/JS chrome + unrelated video titles.
  - GitHub search page → HTML search UI text.

## Quality & grounding
- average_quality_score 0.807; tier_counts {high: 9, medium: 1} — **block page + JS shells scored high** (https + title + connector bonuses; no content-validity signal).
- claim_review: stance **supported**, confidence **high**:
  - `supply_tightness` supported by ev-0005 (TrendForce, legit) + **ev-0010 (YouTube shell)**.
  - `fundamental_leverage` supported by **ev-0010 only** (keyword "record"/"revenue" appearing in unrelated YouTube titles).
  - `price_acceleration` cites ev-0009 (GitHub search page HTML).
- decision_brief action_bias `constructive_but_verify_price_and_valuation` — an investment-leaning bias derived partly from junk evidence.
- 1 directional conflict flag raised (term co-occurrence); did not alter confidence.

## Rubric-relevant scores (evidence at paths above)
Task understanding 3 (pack routed correctly; queries not executed as searches) · Source discovery 2 (all pack-configured; the one autonomous mechanism returned 0) · Primary ratio 3 (6/10 primary-ish) · **Freshness 1** (no dates; stale seeds presented as current; only quotes fresh) · Relevant yield 2 (6/10 relevant) · Domain diversity 3 (finance.yahoo, trendforce, micron + junk domains) · Extraction 2 (4000-char truncation; JS chrome; block page) · Dup suppression 3 (none present; exact-only mechanism) · Conflict handling 2 (flag only) · **Claim-to-citation 1** (buckets cite junk) · Citation validity 2 · Artifact completeness 5 · **Failure transparency 1** (0-row "ok", block page as evidence, 0 warnings overall) · Self-repair 0 (advisory only) · Reproducibility 4 (exact command re-runnable; page content drifts) · Latency 5 (per-request elapsed_ms + wall clock) · Cost unavailable · External fallback 5 (none needed).

Headline per plan rubric: **2/5** — current prices yes, but primary announcements stale & unflagged, and grounding contaminated by junk rows.
