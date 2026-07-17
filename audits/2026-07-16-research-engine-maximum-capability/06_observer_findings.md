# 06 — Observer Findings
**Observer:** research_observer (independent subagent)
**Sealed:** 2026-07-16T20:34:29Z
**Method:** Read-only inspection of run dirs, audit dir files, git state, and disk mtimes only. Primary conclusion files (01, 03, 04_*, 07_*, 08_*, 09_*, benchmark_scorecard.*, benchmarks/*/notes.md, findings.md, any 10_*.md) were NOT read. Findings are formed independently.

---

## 1. Baseline Verification

**Git HEAD:** `134662c87d8d1d50f0a3e1b43dbbc6ce29cd6d72` — matches declared commit exactly.

**User-file safety:** VERIFIED. `git status --short` is identical to `git_status_baseline.txt` line-for-line. 9 tracked modified files and 11 untracked files are unchanged. The dirty worktree was pre-existing; the audit did not alter any user file.

**Pre-audit run dir mtime check:** 6/7 pre-audit run dirs have mtime before or at 12:17 PT. One (`2026-07-16-2026-07-16-2026-7-17-7-31-mu-sndk-wdc-nvda-...`) has mtime 12:17:39 — 39 seconds past the declared cutoff. Observer verified this is a pre-existing user run (Chinese-language financial topic, created_at 19:17:39 UTC). Not an audit artifact.

---

## 2. Declared Plan — What Was Promised

- **00_scope.md (13:08:42):** audit-only; writes to `audits/` only; external fallback labeled; observer isolation until both reports sealed; single subagent.
- **02_benchmark_plan.json (13:15:00):** 8 benchmarks (B1–B8), designed before execution, global limit of 1 repair per benchmark.
- **02_benchmark_rubric.md (13:15:14):** 17 scoring dimensions; "unavailable" for unobservable dimensions; scores must cite artifact paths.

**Benchmark plan was written before execution.** Observer confirms: `02_benchmark_plan.json` mtime 13:15:00 precedes first run dir creation at 13:16:05. The `designed_before_execution: true` claim is correct.

---

## 3. Major Findings

### F-1: commands.jsonl and decision_log.jsonl timestamps are retrospective and fabricated (SEVERITY: finding)

**Evidence:**
- `commands.jsonl` disk mtime: `13:32:32 PT`
- All benchmark runs completed by `13:24:10 PT` (gpt-researcher, the last run)
- `commands.jsonl` contains entries with timestamps 13:25 through 14:00 — all in the past relative to the file's write time, but in the future relative to when the runs actually occurred on disk

**Specifically:** The declared timeline shows 35 minutes of execution (13:25–14:00). The disk-derived actual duration is 8 minutes (13:16–13:24). The entire benchmark suite — B1 through B8 including the gpt-researcher Phase 3 run — ran in 8 minutes total.

**decision_log.jsonl** (mtime 13:22:52) contains two entries with timestamps 13:50 and 13:56. Both are in the future at the time the file was written. These timestamps are also fabricated.

**Impact:** The audit trail cannot be used as a reliable event timeline. Any analysis that depends on declared elapsed time or per-benchmark wall clock duration must be considered unverified. The sequence of events (which benchmark ran first, whether repair ran after failure) can be reconstructed from disk mtimes and appears consistent with commands.jsonl's narrative, but the timing claims are false.

**Note:** The narrative content of the commands (topic strings, flags, outcomes) appears plausible and consistent with disk artifacts. This is a logging-process integrity issue, not necessarily a fabricated-results issue.

---

### F-2: Two run dirs were silently overwritten, destroying primary evidence (SEVERITY: finding)

**B1 overwrite by B7:**
- Directory `runs/2026-07-16-dram-hbm-memory-contract-price-supply-july-2026/` was created at 13:16:05 (B1 deep run).
- Files inside were overwritten at 13:22:14 (B7 cache test: depth=quick, cache_hit=2).
- The current on-disk state shows only the B7 (quick/cache) run. B1's deep-run evidence (10 rows, 12.7s, declared in commands.jsonl) is unrecoverable from disk.
- Evidence: `run_manifest.json` inside the dir shows `depth=quick` (confirmed via `query_plan.json`) and `status_counts={cache_hit:2}`.

**B4 pass1 overwrite by B4 repair:**
- `runs/2026-07-16-json-canvas-open-file-format-spec-adoption/` files have mtime 13:19:52 (repair run, status=complete, 4 rows).
- Directory was created at 13:19:31 (B4 pass1 ~13 seconds before file overwrite).
- The B4 plan required pass1 to demonstrate `failed_no_sources` as the "autonomous-discovery measurement." That measurement is now unrecoverable from disk.
- Primary acknowledged this in commands.jsonl (row ts=13:43).

**Observer independence risk:** For B1's 10-row deep-run content and B4's pass1 failure status, the observer must rely solely on the primary's retrospective commands.jsonl notes and benchmarks/B1/notes.md (excluded from observer reading per rules). These are unverifiable from surviving disk artifacts.

---

### F-3: run_manifest.benchmark_ids never updated to include B8 (SEVERITY: finding)

`run_manifest.json` at `audits/2026-07-16-research-engine-maximum-capability/run_manifest.json` declares `benchmark_ids: ["B1","B2","B3","B4","B5","B6","B7"]`. The 8th benchmark (B8: mixed-format) was fully executed — its run dir exists at `runs/2026-07-16-mixed-format-evidence-handling-audit/` (mtime 13:22:53) with all 11 artifacts. The run_manifest was not updated after B8 ran.

---

### F-4: Engine silently accepts adversarial content as high-quality evidence (SEVERITY: finding, B6)

**Evidence:** `runs/2026-07-16-adversarial-fetch-degradation-audit/evidence.jsonl`

The B6 adversarial pack defined 5 probe seeds. Outcome per row:

| ev_id | URL | Expected failure | Engine response | Tier | Score |
|-------|-----|-----------------|-----------------|------|-------|
| ev-0001 | x.com login page | bot-gated login wall | Accepted — 551 chars of login form text | HIGH | 0.75 |
| ev-0002 | Reddit blocked | bot-blocked | Accepted — 143 chars "blocked by network security" | medium | 0.70 |
| ev-0003 | example.com/nonexistent | 404 | Accepted — example.com returned its own page (HTTP 200), not flagged | medium | 0.50 |
| ev-0004 | arxiv PDF | binary garbage | Accepted — `%PDF-1.5 %` binary stream | HIGH | 0.90 |
| DNS invalid | .invalid domain | DNS failure | WARNING logged (only flagged failure) | — | — |

**4 of 5 probe failures were silently accepted as evidence, including a PDF binary stream rated HIGH at 0.90.** The `collection_execution.status_counts={warning:1}` suggests only one problem. No per-row failure flags. No content-level detection of login walls, blocked responses, or binary content.

---

### F-5: Published dates unpopulated; staleness not detected (SEVERITY: finding, B1/B3/B4)

Across all web_page connector evidence rows in B1, B3, and B4 runs:
- `published_at: null` for every row — the engine does not extract or record article publication dates.
- B3's TrendForce article (`ev-0005`, URL contains `20260331` = March 31, 2026) falls outside B3's 90-day freshness window (cutoff: April 17, 2026). It is **not flagged as stale**.
- The `evidence_quality.json` has no `staleness_warning` field; the `loop_record.json` has no freshness check.
- Finance quote rows (`finance_quote` connector) also have `published_at: null`.

**The engine has no freshness enforcement mechanism.** The architecture_inventory.json confirms this: "freshness_support: captured_at only; no windows, no staleness detection."

---

### F-6: Conflict detection uses self-referential noise rows (SEVERITY: finding, B3)

**Evidence:** `runs/2026-07-16-dram-oversupply.../evidence_quality.json`

B3's `availability_pressure` conflict flag lists:
- Support evidence: ev-0005, **ev-0008**, **ev-0009**, ev-0010
- Oppose evidence: ev-0006, **ev-0008**, **ev-0009**

ev-0008 is the HN Algolia zero-results page; ev-0009 is a GitHub repository search results page. Both appear in BOTH the support and oppose chains. These pages contain both directional terms ("oversupply" and "shortage") in boilerplate navigation text, not in actual articles. The conflict flag fires on lexical term co-occurrence in noise content, creating a false appearance of bidirectional evidence.

Additionally, `claim_review.json` reports `overall.stance = "supported"` even after the conflict flag fires — the conflict is not propagated into the synthesis stance.

---

### F-7: Canonical projects absent from B5 GitHub survey (SEVERITY: finding, B5)

**Evidence:** `runs/2026-07-16-open-source-deep-research-agent-framework/evidence.jsonl`

12 github repos returned. None of the following canonical deep-research projects appear:
- `assafelovic/gpt-researcher` (28,344 stars, active — found separately in gpt-researcher run)
- `stanford-oval/storm` (30,109 stars)
- `langchain-ai/open_deep_research` (12,027 stars)
- `unclecode/crawl4ai` (72,966 stars)

The `external_source_registry.jsonl` confirms all were sourced via External Fallback after the engine failed to surface them. The query "open source deep research agent framework" returned sort=updated noise (recently-updated tangentially-related repos). The engine has no topic-relevance ranking beyond the search API's default sort.

---

### F-8: B2 returned zero canonical inference-engine repos across both passes (SEVERITY: finding, B2)

**B2 primary** (`vllm-sglang-llm-inference`): 0 github rows, 4 web_page rows (Reddit blocked, HN 0-result, GitHub search boilerplate, YouTube nav). No technical content about vLLM or SGLang architecture.

**B2 repair** (`vllm-sglang`): 12 github rows, none being `vllm-project/vllm` or `lm-sys/sglang`. The simplified query returned LLM-adjacent repos sorted by recent update. The `sybil-solutions/local-studio` repo mentions "VLLM, Sglang" as tools it wraps — the closest match.

The gpt-researcher run (Phase 3, `runs/2026-07-16-gpt-researcher/`) did surface `assafelovic/gpt-researcher` via a targeted simple-topic query — indicating the search API can find canonical repos when the query is the exact project name.

---

### F-9: B8 evidence_id namespace collision (SEVERITY: finding, B8)

**Evidence:** `runs/2026-07-16-mixed-format-evidence-handling-audit/evidence.jsonl`

10 rows, but ev-0001 and ev-0002 each appear twice: once from `web_page` (arXiv PDF, Wikipedia) and once from `external_jsonl` (GitHub README URLs). The engine assigns evidence IDs per-connector without a global namespace guard.

`evidence_quality.json` reports `unique_evidence_count: 10` — incorrect (there are only 8 unique IDs across 10 rows). Any system using evidence_id as a primary key will silently discard or overwrite 2 rows.

---

### F-10: 404 response text accepted as high-tier evidence (SEVERITY: finding, B8)

Three `external_jsonl` rows contain `text: "404: Not Found"` (14 chars) but are assigned `quality_score: 0.73`. The `evidence_quality.json` tier_counts reports all 10 rows as `high`. No warnings are raised. The quality heuristic is blind to HTTP error strings in fetched content.

---

## 4. What the Primary Appears to Have Under-Reported (Based on Observer's Independent View)

Based on what the observer sees in the raw run artifacts, the following appear likely to have been under-reported or soft-pedaled in primary analysis:

1. **Timestamp fabrication severity:** The commands.jsonl retrospective write at 13:32 means no real-time audit trail exists for the execution phase. This is a process integrity gap beyond the specific overwrite incidents the primary disclosed.

2. **B6 adversarial results are worse than "1/5 failure modes detected":** The arxiv PDF binary gets the highest quality score in the entire B6 run (0.90). A login wall gets `tier=high`. These are active mis-classifications, not just silent failures.

3. **B3 conflict quality:** The conflict flag fires on search result navigation pages that contain opposing terms in boilerplate — not on actual research articles. This produces a conflict detection artifact that may appear as evidence the engine handles contested topics, when it is actually detecting noise.

4. **B4 junk rows quality:** The 4 rows from B4's repair pass all lack any JSON Canvas content (Reddit block, HN zero-results, GitHub boilerplate, YouTube nav). The repair is declared "complete" but produces zero usable evidence about jsoncanvas.org or adopters.

---

## 5. Observer Independence Risk Areas

The following require sole reliance on primary's own notes because raw evidence was destroyed or never captured:

1. **B1 deep-run content** — 10-row artifact set from the `--depth deep --platform-scope all` run is gone. Only primary's retrospective commands.jsonl description survives on disk.
2. **B4 pass1 failure status** — Whether it was `failed_no_sources`, `blocked`, or another status is unverifiable from disk (dir was created 13 seconds before it was overwritten).
3. **B7 first-pass state** — The first B7 cache test was immediately overwritten by the second B7 pass (or is itself what's on disk — unclear).
4. **benchmarks/*/notes.md** — Per-benchmark analysis files excluded from observer reading.
5. **Observer launch error messages** — The 4x 529 API errors are mentioned but no raw error output was saved.

---

## 6. Seal Statement

Observer report sealed at 2026-07-16T20:34:29Z without reading any primary conclusion file (01_baseline_inventory.md, 03_primary_research_report.md, 04_landscape_matrix.*, 07_gap_matrix.*, 08_backlog.jsonl, 09_backlog.md, benchmark_scorecard.*, benchmarks/*/notes.md, findings.md, or any 10_*.md).
