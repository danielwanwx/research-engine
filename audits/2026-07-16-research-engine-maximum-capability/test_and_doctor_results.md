# Test & Doctor Results (Phase 0)

## pytest (2026-07-16T13:11-07:00)
```
127 passed in 0.19s
```
- Command: `python3 -m pytest -q` (Python 3.14.3, pythonpath=src via pyproject).
- 0.19s total ⇒ no live network tests; connectors tested with mocks/fixtures only.
- 17 test modules incl. new uncommitted ones (test_targets, test_job_discovery, test_web_safety) — all pass against the dirty worktree.

## ruff
- `python3 -m ruff check src tests` → **No module named ruff** (dev extras not installed in system python). Recorded as environment gap; NOT installed per audit rules.

## doctor (`--format json --no-write`, saved: doctor_output.json)
- status: complete_with_warnings; 4/11 available, 0 required failures, 7 optional missing.
- Available: python 3.14.3, research_engine package, `gh`, `playwright` import.
- Missing (optional): agent-reach, twitter, rdt, xhs, xq, yt-dlp, opencli.
- Env: no GROK_API_KEY / XAI_API_KEY ⇒ xai_discovery degrades to warning.

## Implications for benchmarking
- Engine's real usable connector surface on this machine: web_page (+playwright), finance_quote, github_public_search, manual, external_jsonl, official_job_discovery. Bridges and xAI discovery will produce warnings, not evidence — that itself is benchmark evidence for graceful degradation (B6) and discovery ceiling (B4).
