# 10 — Final Recommendation

## Verdict in one paragraph
Research Engine v0.1.0 is a well-built **evidence bookkeeping layer** wrapped around a collection capability that does not yet exist for open-ended research. Its artifact discipline, stop-reason vocabulary, safety posture, and telemetry are genuinely above-average (the parts most projects skip). But benchmarks show it cannot discover sources autonomously (B2/B4/B5), cannot tell garbage from evidence (B1/B6/B8 — a PDF binary was the *highest-scored* row in its run), has no notion of time (B1), destroys its own history on rerun (B4/B7), and its claim verdicts amplify these failures into confident, decision-flavored output (B1/B3). Median benchmark score: 1/5.

## The five ceiling blockers
1. **Validity blindness** — anything fetched without an exception becomes evidence; quality scoring then promotes it (RB-001/004).
2. **No autonomous retrieval** — no web search, cosmetic query plans, recency-sorted GitHub noise (RB-005/006/007).
3. **Time blindness** — no published_at, no as-of windows, stale seeds presented as current (RB-008).
4. **Non-durable runs** — silent overwrites, colliding evidence ids, no journal (RB-002/003/019).
5. **No measurement** — zero eval harness, so none of the above can be shown fixed (RB-010).

## Recommended sequence
- **M0 (Trust & Measurement)**: RB-001, RB-002, RB-003, RB-004, RB-019, RB-010. Small, mostly S/M effort, removes every "systematically misleading" behavior and makes progress measurable. Nothing else should ship before M0.
- **M1 (Discovery & Retrieval)**: RB-005 (pluggable retriever, SearXNG key-free default), RB-006, RB-007. This is where the engine starts being able to answer unseeded questions.
- **M2 (Evidence Intelligence & Repair)**: RB-008, RB-009, RB-011, RB-012, RB-015.
- **M3 (Memory & Scale)**: RB-014, RB-016, RB-017. — **M4 (Ecosystem)**: RB-018.

## How to prove it worked
Re-run this audit's benchmark suite (02_benchmark_plan.json; fixtures under fixtures/) after each milestone. M0 exit = B6 detects 5/5 probes, no claim cites an invalid row, rerun collisions impossible. M1 exit = B4 finds jsoncanvas without a pack; B2 surfaces vllm/sglang canonical repos. Commit the suite as the repo's first regression eval (RB-010) so these are CI-checkable, using BrowseComp-Plus's fixed-corpus philosophy for the offline subset.

## What NOT to do (see 09_backlog.md "Do Not Build Yet")
No multi-agent orchestration, no embedded LLM judging, no embeddings, no AGPL vendoring, no framework dependencies, no monitoring daemon — each is either premature before M0–M2, unfalsifiable without RB-010, or license/architecture-incompatible.

## Confidence & unknowns
Engine defects: FACT, double-verified (primary + sealed observer). B1-deep/B4-pass1 details: single-witness (engine overwrote the bundles — itself a P0 exhibit). Audit timeline durations: reduced precision (10_reconciliation.md #1). Untested on this machine: xAI discovery with a real key, AgentReach/OpenCLI bridges with upstream tools installed — their *degradation* behavior is verified, their happy path is UNKNOWN.
