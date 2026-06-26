# Research Engine Loop Harness Implementation Plan

Date: 2026-06-26
Status: Draft implementation plan
Spec: `docs/superpowers/specs/2026-06-26-research-engine-loop-harness-design.md`

## Objective

Implement the approved loop/harness design incrementally while keeping
`research-engine` usable after every slice. The implementation should preserve
the current source-agnostic core and add optional capability bridges, loop
state, reflection, memory, and evals around it.

The first implementation pass should prioritize:

1. Open-source readiness and explicit capability detection.
2. Optional upstream bridges for AgentReach/OpenCLI/web crawling/browser
   sampling.
3. A deterministic loop wrapper around the existing one-shot runner.
4. Persistent, inspectable research memory.
5. A lightweight eval harness that prevents regressions in evidence quality.

## Working Rules

- Keep `research-engine run` backward compatible.
- Keep optional collectors optional. Missing AgentReach/OpenCLI/browser tools
  must produce warnings, not crashes.
- Do not store cookies, tokens, browser profiles, broker credentials, or
  paywalled content in the repo.
- Add tests with each behavioral change.
- Prefer small modules over one large loop orchestrator.
- Write deterministic artifacts before any optional LLM judge step.
- Commit each completed slice separately.

## Slice 0: Development Hygiene And Open-Source Readiness

Purpose:

- Make the repo easier to install, test, and understand before deeper features
  land.

Files to touch:

- `README.md`
- `pyproject.toml`
- Optional: `Makefile`
- Optional: `docs/connector-support.md`

Tasks:

1. Update README positioning:
   - Tagline: "Evidence-first research loops for AI agents."
   - Explain how Research Engine differs from AgentReach and OpenCLI.
   - Explain that AgentReach/OpenCLI are optional upstream capability providers.
2. Clarify dev setup:
   - Python `>=3.10`.
   - `python -m pip install -e '.[dev]'`.
   - `python -m pytest -q`.
   - `python -m ruff check src tests`.
3. Add a connector support matrix:
   - `manual`
   - `external_jsonl`
   - `web_page`
   - `finance_quote`
   - `agent_reach_bridge`
   - planned `opencli_bridge`
   - planned `web_crawler`
   - planned `chrome_platform_sampler`
4. Add optional command helpers only if they reduce ambiguity:
   - `make test`
   - `make lint`
   - `make check`

Tests:

- Run `python -m pytest -q` in a Python 3.10+ environment.
- Run `python -m ruff check src tests` if ruff is installed.

Acceptance:

- A new contributor can install and test the package from README alone.
- README clearly states what the project is and is not.

## Slice 1: Doctor Command And Capability Registry

Purpose:

- Make optional upstream capability status explicit and machine-readable.

New files:

- `src/research_engine/doctor.py`
- `src/research_engine/state.py`
- `tests/test_doctor.py`
- `tests/test_state.py`

Files to update:

- `src/research_engine/cli.py`
- `README.md`

Data artifacts:

- `state/connector_capabilities.json`

Tasks:

1. Add a `CapabilityCheck` data shape:
   - `id`
   - `label`
   - `available`
   - `version`
   - `path`
   - `warning`
   - `metadata`
2. Add doctor checks:
   - Python version.
   - Package importability for core package.
   - Optional commands: `agent-reach`, `twitter`, `rdt`, `xhs`, `xq`, `yt-dlp`,
     `gh`, `opencli`.
   - Optional browser dependencies: Playwright importability only if requested.
3. Add CLI commands:
   - `research-engine doctor`
   - `research-engine doctor agentreach`
   - `research-engine doctor opencli`
4. Write capability output to JSON:
   - Default path: `state/connector_capabilities.json`.
   - Allow override: `--state-dir`.
5. Keep output human-readable on stdout and structured in the JSON artifact.

Tests:

- Mock `shutil.which`.
- Mock version command execution.
- Verify missing tools produce `available: false` and warnings.
- Verify JSON artifact is written.
- Verify CLI exits `0` when optional tools are missing.

Acceptance:

- Users can see exactly which optional upstream tools are available.
- Missing optional tools do not fail the package.

## Slice 2: AgentReach Bridge Upgrade

Purpose:

- Turn the current bridge into a broader, doctor-aware upstream connector.

Files to update:

- `src/research_engine/connectors/agent_reach.py`
- `src/research_engine/platforms.py`
- `tests/test_agent_reach.py`
- `README.md`

Tasks:

1. Expand default platform command templates:
   - X/Twitter
   - Reddit
   - GitHub
   - YouTube
   - Xiaohongshu
   - Xueqiu
   - Bilibili
   - RSS
   - Jina Reader/open web where safely supported
2. Add per-platform tool metadata:
   - required executable
   - expected output format
   - access mode
   - safety notes
3. Improve warnings:
   - missing executable
   - command timeout
   - non-zero exit
   - unparseable output
4. Record command provenance in evidence rows:
   - command
   - platform
   - query
   - access mode
5. Keep custom `--agent-reach-command` behavior backward compatible.

Tests:

- Command rendering for each platform.
- Structured JSON output parsing.
- JSONL output parsing.
- Plain text fallback.
- Missing executable warning.
- Command failure warning.

Acceptance:

- The bridge can support AgentReach-installed tools without requiring the
  `agent-reach` command itself.
- Evidence rows remain normalized and auditable.

## Slice 3: OpenCLI Bridge

Purpose:

- Add a connector for OpenCLI-powered browser workflows and adapters.

New files:

- `src/research_engine/connectors/opencli.py`
- `tests/test_opencli.py`

Files to update:

- `src/research_engine/connectors/__init__.py`
- `src/research_engine/runner.py`
- `src/research_engine/platforms.py`
- `README.md`

Connector id:

- `opencli_bridge`

Source config shape:

```json
{
  "source_id": "x_loop_seed_feed",
  "connector": "opencli_bridge",
  "platform": "x",
  "command": "opencli x search --query {query} --format json",
  "query": "loop engineering",
  "timeout_seconds": 60
}
```

Tasks:

1. Implement command rendering with placeholders:
   - `{query}`
   - `{platform}`
   - `{max_results}`
2. Detect `opencli` with `shutil.which`.
3. Execute command with timeout and no shell.
4. Parse JSON, JSONL, and plain text.
5. Normalize rows with:
   - `connector: opencli_bridge`
   - `platform`
   - `title`
   - `url`
   - `text`
   - `source_kind`
   - `access_mode`
   - `metrics.command`
6. Add docs explaining that OpenCLI recipes must not include secrets.

Tests:

- Missing command.
- Non-zero exit.
- JSON object output.
- JSON array output.
- JSONL output.
- Plain text fallback.
- Max result limiting.

Acceptance:

- A user can wire an OpenCLI command into a research pack without changing core
  runner code.

## Slice 4: Web Crawler Connector

Purpose:

- Reuse the stronger crawler pattern from `web-to-podcast` for source discovery
  beyond static seed pages.

New files:

- `src/research_engine/connectors/web_crawler.py`
- `tests/test_web_crawler.py`
- `tests/fixtures/web_crawler/`

Files to update:

- `src/research_engine/connectors/__init__.py`
- `src/research_engine/runner.py`
- `pyproject.toml`
- `README.md`

Connector id:

- `web_crawler`

Tasks:

1. Implement stdlib static fetch first:
   - seed URLs
   - timeout
   - user agent
   - headers
2. Add sitemap parsing.
3. Add bounded same-domain crawl:
   - `start_urls`
   - `max_pages`
   - `same_domain`
   - `include_patterns`
   - `exclude_patterns`
4. Add basic text extraction:
   - title
   - visible-ish text from HTML
   - links metadata when useful
5. Add optional Playwright renderer behind extras:
   - `pip install -e '.[browser]'`
   - storage-state path reference only
6. Preserve politeness controls:
   - timeout
   - max pages
   - delay
7. Emit raw debug metadata without storing secrets.

Tests:

- Static HTML fetch with mocked opener or local fixture.
- Sitemap parsing.
- Include/exclude pattern behavior.
- Same-domain crawl bound.
- Duplicate URL suppression.
- Playwright missing dependency warning path.

Acceptance:

- Public site crawl can produce multiple normalized evidence rows.
- Browser rendering is optional and safe when absent.

## Slice 5: External Evidence And Authorized Browser Ingestion

Purpose:

- Make logged-in and private-source evidence easy to ingest without coupling
  core code to a local browser profile.

Files to update:

- `src/research_engine/connectors/external.py`
- `README.md`
- `tests/test_connectors.py`

Optional new docs:

- `docs/authorized-evidence.md`

Tasks:

1. Expand accepted external row fields:
   - `platform`
   - `author`
   - `published_at`
   - `captured_at`
   - `source_kind`
   - `source_confidence`
   - `access_mode`
   - `metrics`
2. Add clearer warnings for:
   - missing title/text/url
   - missing platform
   - private source without access mode
3. Document JSONL examples:
   - Lenny member content capture.
   - X visible search result capture.
   - LinkedIn visible post capture.
4. Add examples for safe handling:
   - do not commit exports with private content unless intended.
   - do not include cookies or auth headers.

Tests:

- Normalize richer external rows.
- Warn on weak rows.
- Preserve metadata.

Acceptance:

- Authorized evidence can be imported cleanly even before Chrome/OpenCLI bridges
  are fully implemented.

## Slice 6: Chrome Platform Sampler Bridge

Purpose:

- Expose local authorized, read-only platform sampling as an optional connector.

New files:

- `src/research_engine/connectors/chrome_sampler.py`
- `tests/test_chrome_sampler.py`

Files to update:

- `src/research_engine/connectors/__init__.py`
- `src/research_engine/runner.py`
- `README.md`

Connector id:

- `chrome_platform_sampler`

Tasks:

1. Keep the connector optional and local-only.
2. Do not import `Agentic Engineer` directly as a required dependency.
3. Support two safe modes:
   - command mode: call a user-configured local sampler command that emits JSONL.
   - external mode: import JSONL captured by a separate browser workflow.
4. Document a future port of the read-only Chrome sampler logic from
   `Agentic Engineer`.
5. Enforce read-only semantics in docs and connector naming.

Tests:

- Missing configured command warning.
- JSONL command output parsing.
- Command failure warning.
- Row normalization.

Acceptance:

- Research packs can reference a local Chrome sampler without making browser
  access part of the open-source core.

## Slice 7: Loop Engineering Research Pack And X Seed Group Config

Purpose:

- Add a reusable pack for researching loop/harness engineering itself and seed
  it with the user's X account group pattern.

New files:

- `src/research_engine/default_packs/loop_engineering.json`
- `tests/test_loop_engineering_pack.py`
- Optional: `examples/x_seed_groups/loop_engineering.json`

Files to update:

- `README.md`
- `src/research_engine/platforms.py`

Tasks:

1. Add `loop_engineering` pack:
   - match terms
   - query templates
   - claim specs
   - matrix nodes
   - quality/conflict rules where useful
2. Add claim specs:
   - durable state/memory.
   - harness over prompting.
   - verifier as core loop component.
   - connectors as upstream sources, not final truth.
   - human gate for logged-in/high-side-effect work.
3. Add example X seed group config:
   - `shrik1645608`
   - `RohOnChain`
   - `svpino`
   - loop/harness/self-improving keywords
4. Keep the config as an example, not a default account dependency.

Tests:

- Pack loads.
- Auto-selects for loop/harness prompts.
- Claim specs score against mocked evidence.

Acceptance:

- `research-engine run "research loop engineering"` routes to the new pack.

## Slice 8: Verification Report Layer

Purpose:

- Promote quality checks from evidence scoring into a broader verification
  artifact.

New files:

- `src/research_engine/verification.py`
- `tests/test_verification.py`

Files to update:

- `src/research_engine/runner.py`
- `src/research_engine/artifacts.py`
- `tests/test_runner.py`

New artifact:

- `verification_report.json`

Tasks:

1. Build verification from:
   - evidence rows
   - quality report
   - execution report
   - pack requirements
2. Detect:
   - missing required source categories
   - low source diversity
   - stale evidence
   - unsupported claims
   - conflicting evidence
   - connector partial failures
3. Add severity levels:
   - `info`
   - `warning`
   - `blocker`
4. Add report summary:
   - `status`
   - `confidence`
   - `coverage_score`
   - `blocking_issues`

Tests:

- No evidence blocker.
- Low diversity warning.
- Connector failure warning.
- Conflict flag carried forward.
- Strong evidence produces passing verification.

Acceptance:

- Every run has a verification report before synthesis is consumed.

## Slice 9: Reflection

Purpose:

- Decide whether a run should stop, rerun deeper, ask for user input, or be
  monitored.

New files:

- `src/research_engine/reflection.py`
- `tests/test_reflection.py`

Files to update:

- `src/research_engine/runner.py`
- `src/research_engine/artifacts.py`
- `tests/test_runner.py`

New artifact:

- `reflection.json`

Tasks:

1. Add deterministic reflection rules:
   - no rows -> `failed`
   - verification blockers -> `needs_more_evidence`
   - missing authorized sources -> `needs_user_input`
   - high confidence and good coverage -> `complete`
   - time-sensitive thesis -> `monitor`
2. Generate:
   - follow-up queries
   - recommended connectors
   - user questions
   - next-run spec
3. Include reflection in run manifest summary.

Tests:

- Complete path.
- Needs more evidence path.
- Needs user input path.
- Monitor path.
- Failed path.

Acceptance:

- A run produces an explicit next-action recommendation.

## Slice 10: Persistent Memory

Purpose:

- Store inspectable research state across runs.

New files:

- `src/research_engine/memory.py`
- `tests/test_memory.py`

Files to update:

- `src/research_engine/cli.py`
- `README.md`

State files:

- `state/thesis_ledger.jsonl`
- `state/source_registry.json`
- `state/open_questions.jsonl`
- `state/claim_history.jsonl`

Tasks:

1. Implement `ResearchMemory` with configurable `state_dir`.
2. Add append/update helpers:
   - thesis ledger append.
   - open question append.
   - source registry update.
   - claim history append.
3. Add CLI:
   - `research-engine remember runs/<run_id>`
4. Add idempotency where possible:
   - avoid duplicate source registry entries.
   - preserve append-only thesis history.
5. Add drift helper:
   - compare latest thesis stance/confidence to previous state.

Tests:

- Empty state creation.
- Remember run writes expected files.
- Source registry update is stable.
- Thesis ledger is append-only.
- Drift detection detects stance/confidence changes.

Acceptance:

- A completed run can be persisted into state without hidden databases.

## Slice 11: Loop Runtime

Purpose:

- Wrap existing one-shot runs into an explicit loop artifact with iterations.

New files:

- `src/research_engine/loop.py`
- `tests/test_loop.py`

Files to update:

- `src/research_engine/cli.py`
- `src/research_engine/runner.py` if needed for reusable lower-level calls.
- `README.md`

New command:

```bash
research-engine loop "research DRAM HBM supply shortage"
```

Tasks:

1. Implement `ResearchLoop` wrapper.
2. Create layout:
   - `loops/<loop_id>/loop_manifest.json`
   - `loops/<loop_id>/loop_plan.json`
   - `loops/<loop_id>/iterations/001-<run_id>/`
3. Run one iteration first.
4. Use `reflection.json` to decide whether another iteration is allowed.
5. Add guardrails:
   - `--max-iterations`, default 1 or 2.
   - `--dry-run`.
   - no automatic logged-in collector use without explicit flags/config.
6. Optionally call `remember` at the end with `--remember`.

Tests:

- Dry-run loop creates loop artifacts.
- One-iteration complete path.
- Needs-more-evidence stops at max iteration.
- Backward compatibility for `run`.

Acceptance:

- Users can run a bounded research loop without changing existing one-shot
  behavior.

## Slice 12: Discovery

Purpose:

- Convert watchlists and seed groups into research candidates.

New files:

- `src/research_engine/discovery.py`
- `tests/test_discovery.py`
- Optional: `examples/watchlists/loop_engineering.json`

Files to update:

- `src/research_engine/cli.py`
- `README.md`

New command:

```bash
research-engine discover --watchlist state/watchlists.json
```

Tasks:

1. Define watchlist schema:
   - topics
   - accounts
   - keywords
   - platforms
   - trigger thresholds
2. Generate `discovery_candidates.json`.
3. Support static config discovery first.
4. Leave live platform fetching to connectors or external evidence.
5. Add candidate scoring:
   - freshness
   - source priority
   - estimated impact
   - unresolved-question match

Tests:

- Watchlist parsing.
- Candidate generation.
- Candidate scoring.
- Empty watchlist behavior.

Acceptance:

- Discovery can suggest loop runs without live browser/API access.

## Slice 13: Eval Harness

Purpose:

- Add regression checks for evidence quality, connector failures, and synthesis
  integrity.

New files:

- `src/research_engine/evals.py`
- `tests/test_evals.py`
- `tests/fixtures/evals/`

Files to update:

- `src/research_engine/cli.py`
- `README.md`

New command:

```bash
research-engine eval
```

Tasks:

1. Define eval case schema:
   - input topic
   - pack id
   - mock connector rows
   - expected quality/verification outcomes
2. Add built-in cases:
   - generic research
   - memory cycle
   - loop engineering
   - conflicting evidence
   - duplicate evidence
   - missing optional tool
3. Output:
   - pass/fail
   - coverage score
   - citation quality score
   - conflict detection score
   - regression summary
4. Keep eval deterministic.

Tests:

- Eval runner passes fixture cases.
- Intentional failing case reports clear failure.

Acceptance:

- `research-engine eval` can catch regressions before pushing the repo.

## Slice 14: Optional LLM Judge

Purpose:

- Add a clearly optional judge layer after deterministic artifacts exist.

New files:

- `src/research_engine/llm_judge.py`
- `tests/test_llm_judge.py`

Files to update:

- `src/research_engine/cli.py`
- `README.md`
- `pyproject.toml` only if an optional extra is needed.

Tasks:

1. Keep judge disabled by default.
2. Accept a provider abstraction or external command.
3. Feed only:
   - evidence rows
   - verification report
   - research report
4. Produce:
   - `llm_judge_report.json`
   - `llm_judge_report.md`
5. Require explicit flag:
   - `--llm-judge`

Tests:

- Mock provider.
- Unsupported claim detection.
- Missing provider warning.
- Disabled by default.

Acceptance:

- LLM judging improves review quality without compromising deterministic core.

## Suggested Commit Sequence

1. `docs: update open-source positioning`
2. `feat: add doctor capability registry`
3. `feat: expand AgentReach bridge`
4. `feat: add OpenCLI bridge connector`
5. `feat: add web crawler connector`
6. `docs: document authorized evidence workflows`
7. `feat: add Chrome sampler bridge`
8. `feat: add loop engineering research pack`
9. `feat: add verification report`
10. `feat: add reflection artifact`
11. `feat: add persistent research memory`
12. `feat: add bounded loop runtime`
13. `feat: add discovery command`
14. `feat: add eval harness`
15. `feat: add optional LLM judge`

## First Implementation Recommendation

Start with Slice 0 and Slice 1.

Reason:

- They do not disturb current connector behavior.
- They make the project easier to run and debug.
- They create the capability registry that later AgentReach/OpenCLI/Chrome
  bridges can reuse.

After Slice 1, implement Slice 3 before the larger web crawler. OpenCLI is a
small connector with high leverage for logged-in/no-API websites, while the web
crawler has a larger testing and dependency surface.

## Stop Points

Good stopping points:

- After Slice 1: open-source baseline and doctor complete.
- After Slice 4: major collection bridges complete.
- After Slice 9: one-shot run has verification and reflection.
- After Slice 11: full bounded research loop exists.
- After Slice 13: project has regression evals.

Each stop point should have:

- passing tests
- clean git status
- README or docs updated for new commands
- one example command the user can run locally
