# B4 — Niche topic, no pack/seed (JSON Canvas adoption)

## Pass 1 (defaults)
- Command: `... run "JSON Canvas open file format spec adoption" --pack auto --depth deep --source-timeout-seconds 30` (0.07s)
- Result: **failed_no_sources / blocked / no_executable_sources**, 6 feedback actions. Honest, fast, explicit — this failure path is the engine's best transparency behavior.
- FACT: any topic that matches no pack and gets no flags cannot collect anything (generic pack `sources: []`).

## Repair pass (single, per plan: add --platform-scope all --web-search-pages)
- Command: same topic + `--platform-scope all --web-search-pages` (11.8s)
- **Artifact destruction**: run_id = date+slug(topic) → identical to pass 1 → the repair pass silently OVERWROTE the pass-1 run directory. The failed_no_sources loop_record no longer exists on disk (loop_record.generated_at now 20:19:52Z, status complete). No run versioning, no collision detection, no append. (Pass-1 output preserved only in this audit's commands.jsonl/terminal capture.)
- Evidence: 4 rows, all platform junk (Reddit block page, HN shell, GitHub search UI incl. GitHub marketing copy, YouTube chrome). github_public_search again "ok"/0 rows.
- Zero facts about JSON Canvas: jsoncanvas.org never discovered, obsidianmd/jsoncanvas repo never found, no adopter list. Autonomous discovery capability for unseeded topics ≈ 0.

## Rubric
Task understanding 2 · **Source discovery 0** (nothing autonomous even with every flag) · Primary ratio 0 · Freshness unavailable · Relevant yield 0 · Diversity 1 · Extraction 1 · Dup 3 · Conflict unavailable · Claim-citation 2 (generic honest "needs_analysis") · Citation validity 1 · Artifact completeness 3 (**pass-1 bundle destroyed by overwrite**) · Failure transparency 3 (pass1 5/5; repair "complete" on junk 1/5; overwrite silent 0) · Self-repair 0 · **Reproducibility 2** (same command twice = destroyed history) · Latency 5 · Cost unavailable · Fallback n/a.

Headline per plan rubric: **1/5** (irrelevant rows only; spec repo never found).
