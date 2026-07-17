# 03 — Ecosystem Research Report (Phase 3, self-hosting test)

## Self-hosting result: the engine cannot research its own field (FACT)

Protocol required using the Research Engine first. Attempts:
1. **B5** `"open source deep research agent framework" --depth audit --platform-scope all` → 12 GitHub rows, 6 with ≤2 stars, zero canonical projects (benchmarks/B5/notes.md).
2. **B2** deep technical comparison → zero technical content (benchmarks/B2/notes.md).
3. **Named-repo probe** `"gpt-researcher"` → found assafelovic/gpt-researcher (28,344★) among 7 noise rows. Exact-name lookup works; topical discovery does not.

Verdict: for ecosystem research the engine surfaces recently-pushed noise (sort=updated), cannot fetch docs/articles without seed URLs, and extracts no license/release/maintenance data. Everything below is therefore **External Fallback (Gap Evidence)**:
- What the engine missed: every canonical system in 04_landscape_matrix.csv.
- How external tools found them: public GitHub REST API by exact name (license/stars/pushed in one call — fields the connector already downloads but discards or never requests) + general web search with relevance ranking + article fetching.
- Why the engine's planner/connectors could not: no web-search connector; GitHub connector uses recency sort and repo-search endpoint only; no article/doc fetch without pack seeds; queries in query_plan are never executed.
- Where the gaps belong: web search → **Core connector**; GitHub repo detail (license/releases) → **Connector enrichment**; article fetch for arbitrary URLs → already exists (web_page) but is unreachable without discovery → **Core planning**; ranking → **Core (quality/rerank)**.

## Landscape (as of 2026-07-16; full registry in external_source_registry.jsonl)

| System | License | Stars | Pushed | Most transferable pattern |
|---|---|---|---|---|
| firecrawl | AGPL-3.0 | 151,958 | 07-16 | crawl→render→markdown API (interface only; AGPL) |
| deer-flow (ByteDance) | MIT | 77,212 | 07-16 | enforced human plan-review gate before execution |
| crawl4ai | Apache-2.0 | 72,966 | 07-15 | markdown-first extraction, content-type awareness, bounded crawl strategies |
| searxng | AGPL-3.0 | 33,987 | 07-16 | self-hosted key-free metasearch → JSON API |
| storm (Stanford) | MIT | 30,109 | 2025-09 | multi-perspective question generation; outline-first grounded synthesis |
| smolagents (HF) | Apache-2.0 | 28,388 | 07-14 | minimal tool surface (already aligned) |
| gpt-researcher | Apache-2.0 | 28,344 | 07-16 | planner/executor split; pluggable retriever interface |
| open_deep_research (LangChain) | MIT | 12,027 | 07-16 | supervisor + parallel researchers; checkpoint/replay |

First-party engineering references:
- **Anthropic, "How we built our multi-agent research system"** (anthropic.com/engineering/multi-agent-research-system, retrieved 2026-07-16): orchestrator-worker; explicit effort-scaling rules (simple query → 1 agent/3–10 tool calls); documented failure modes (over-spawning, endless search for nonexistent sources); eval-first development with LLM-judge rubrics. Their +90.2% multi-agent gain is their own internal eval — treated as a marketing-adjacent claim, not independent evidence.
- **Evaluation systems**: DeepResearch Bench (RACE report quality + FACT citation grounding; Bench II, arXiv 2601.08536: 132 tasks/22 domains/9,430 binary rubrics); BrowseComp (OpenAI, live-web, 1,266 questions); BrowseComp-Plus (texttron, ACL 2026: fixed ~100K-doc corpus isolating retriever from agent — the best template for this repo's deterministic test philosophy).

## Transferable methods mapped to reproduced failures

| Reproduced failure (benchmark) | Proven external method | Source (license) |
|---|---|---|
| No topical discovery (B2/B4/B5) | metasearch connector; pluggable retriever interface | SearXNG (service), GPT Researcher (Apache-2.0) |
| Verbatim single query (B2) | perspective/sub-question decomposition before retrieval | STORM (MIT) |
| Junk pages scored high (B1/B6/B8) | markdown extraction + content-type checks + block-page detection | Crawl4AI (Apache-2.0) |
| No license/maintenance data (B5) | repo-detail enrichment (one API call; fields already in payload) | GitHub REST (public) |
| No replay/versioned runs (B4/B7) | checkpointed graph state; run versioning | open_deep_research (MIT) |
| No eval harness (all) | fixed-corpus benchmark + citation-grounding metric | BrowseComp-Plus, DeepResearch Bench |
| Advisory-only feedback (B2/B4) | bounded self-repair loops with no-progress detection | GPT Researcher / deer-flow patterns (Apache-2.0/MIT) |

Not adopted (and why): full multi-agent orchestration (cost ~15x per Anthropic's own article; the engine's value is deterministic auditability under an LLM, not being an LLM agent itself); Firecrawl code reuse (AGPL-3.0 incompatible with MIT vendoring — interface emulation or external-service connector only); LangChain/LlamaIndex/Haystack as dependencies (engine's zero-dependency stance is a legitimate differentiator).
