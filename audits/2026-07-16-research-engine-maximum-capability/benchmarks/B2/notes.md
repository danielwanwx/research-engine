# B2 — Deep technical research (vLLM vs SGLang)

## Pass 1 (primary)
- Command: `... run "vLLM SGLang LLM inference engine architecture comparison" --pack auto --depth audit --platform-scope all --web-search-pages --source-timeout-seconds 30` (11.5s)
- Run dir: `runs/2026-07-16-vllm-sglang-llm-inference-engine-architecture-comparison`
- Result: status **complete**, 4 rows — **zero technical content**. github_public_search sent the 7-word topic verbatim → 0 rows, status "ok", no warning. The 4 rows are the same junk set as B1 (Reddit block page 143 chars, HN 0-results shell, GitHub search UI text, YouTube chrome).
- query_plan `queries` lists 3 tiered queries — none executed by any connector (planned-vs-executed drift is structural: packs.py:65 queries are cosmetic).

## Repair pass (1 allowed; trigger: zero relevant rows)
- Command: `... run "vLLM SGLang" --pack auto --depth audit --platform-scope all --web-search-pages ...` (12.2s)
- Run dir: `runs/2026-07-16-vllm-sglang`
- Result: 16 rows, 12 from GitHub — **but neither vllm-project/vllm nor sgl-project/sglang is among them**. Cause: connector uses `sort=updated&order=desc` (github_public.py:53-58), so freshly-pushed low-relevance repos (five 0-star projects, a VS Code plugin in Russian) outrank the canonical repos. No best-match ranking, no authority weighting, no query decomposition (one query for a two-project comparison).
- Still zero docs/papers/release/architecture text. "Deep technical research" is effectively out of reach.

## Before/after
- Before: 4 rows, 0 relevant. After: 16 rows, ~4 marginally relevant (dynamo, InferenceX, GPTQModel, smg are inference-adjacent), 0 on-target. Repair (manual query simplification by the operator — the engine has no such loop) improved yield but not relevance.

## Rubric scores
Task understanding 1 (no decomposition; comparison intent lost) · Source discovery 1 · Primary ratio 0 (no official sources) · Freshness 2 (github updated_at present; nothing else) · Relevant yield 1 · Domain diversity 1 (github + junk) · Extraction 2 · Dup suppression 3 · Conflict handling unavailable · Claim-to-citation 2 (generic bucket, honest "needs_analysis") · Citation validity 2 · Artifact completeness 5 · Failure transparency 1 (complete status on zero-content run) · Self-repair 0 (operator-driven) · Reproducibility 4 · Latency 5 · Cost unavailable · External fallback n/a (none used; engine failure recorded as gap, not silently patched).

Headline per plan rubric: **1/5**.
