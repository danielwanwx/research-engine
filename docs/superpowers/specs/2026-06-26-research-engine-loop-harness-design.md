# Research Engine Loop Harness Design

Date: 2026-06-26
Status: Draft spec
Owner: Research Engine

## Summary

Research Engine should become an evidence-first research loop engine for AI
agents. The current project already has the core harness shape: research packs,
connector execution, normalized evidence rows, quality reports, claim review,
decision briefs, and traceable run artifacts. The next design step is to turn
this one-shot research runner into a loop system that can discover, plan,
collect, verify, synthesize, reflect, remember, and rerun.

This is not a plan to compete with general-purpose agent runtimes such as
LangGraph, CrewAI, or the OpenAI Agents SDK. Research Engine's useful niche is
more specific:

> Evidence-first research orchestration and verification for agents.

AgentReach, OpenCLI, local browser collectors, public web crawlers, and APIs
should be upstream capabilities. Research Engine should be the layer that
decides what to ask, records where evidence came from, scores source quality,
finds conflicts, produces auditable artifacts, and turns every run into better
state for the next run.

## References

- Addy Osmani, Loop Engineering: https://addyosmani.com/blog/loop-engineering/
- OpenAI, Harness engineering: https://openai.com/index/harness-engineering/
- AgentReach: https://github.com/Panniantong/Agent-Reach
- OpenCLI: https://github.com/jackwener/opencli
- LangGraph: https://github.com/langchain-ai/langgraph
- CrewAI: https://github.com/crewAIInc/crewAI
- OpenAI Agents SDK: https://github.com/openai/openai-agents-python
- Inspect AI: https://github.com/UKGovernmentBEIS/inspect_ai
- User-provided X seed feed: `@shrik1645608` profile timeline screenshot, including
  Roan `@RohOnChain` loop-engineering quant trading content and Santiago
  `@svpino` self-learning agent / harness-layer content.

## Current State

The standalone project lives at:

`/Users/danielwan/Project/AgentProject/research-engine`

Current strengths:

- Pack-driven topic routing through JSON research packs.
- Connector interface with bounded execution, retries, and optional caching.
- Built-in connectors for manual rows, external JSONL, public web pages,
  finance quotes, and an optional AgentReach/upstream CLI bridge.
- Platform planning for web, X, Reddit, Hacker News, GitHub, YouTube,
  LinkedIn, Xiaohongshu, Bilibili, Weibo, WeChat, V2EX, Xueqiu, Lenny, and RSS.
- Deterministic artifacts: `query_plan.json`, `collection_execution.json`,
  `evidence.jsonl`, `evidence_quality.json`, `claim_review.json`,
  `supply_demand_matrix.json`, `decision_brief.json`, and
  `research_report.md`.
- Quality scoring, duplicate clustering, and directional conflict flags.
- A clean stdlib-first shape that is publishable as an open-source package.

Current limits:

- The runner is one-shot. It does not automatically decide whether another
  collection or verification pass is needed.
- There is no persistent research memory across runs.
- The AgentReach bridge is optional but shallow. It detects command output, but
  does not yet run a capability doctor across the broader AgentReach ecosystem.
- OpenCLI is not integrated.
- The stronger local crawler from `web-to-podcast` is not yet exposed as a
  Research Engine connector.
- The logged-in Chrome sampler from `Agentic Engineer` is not yet exposed as a
  Research Engine connector.
- There is no benchmark/eval harness that scores whether a run produced a
  complete, reliable, and non-hallucinatory research pack.

## Product Positioning

### GitHub Tagline

Evidence-first research loops for AI agents.

### README Positioning

Research Engine turns heterogeneous evidence from web pages, browser sessions,
CLI tools, APIs, and manual captures into auditable research artifacts that
agents and LLMs can analyze, verify, and improve over time.

### Differentiation

Research Engine is different from AgentReach and OpenCLI:

- AgentReach installs and exposes upstream platform CLIs.
- OpenCLI turns websites and browser workflows into CLI-accessible capabilities.
- Research Engine orchestrates research intent, evidence normalization,
  quality scoring, contradiction checks, synthesis artifacts, and loop memory.

Research Engine is different from LangGraph, CrewAI, and generic agent
runtimes:

- General agent runtimes coordinate arbitrary state machines, crews, handoffs,
  and tools.
- Research Engine focuses on one domain: evidence-grounded research loops.
- Research Engine can later run inside or alongside a general runtime, but it
  should remain useful as a standalone CLI/library.

## Goals

1. Keep Research Engine source-agnostic.
   All external collection systems enter through connector contracts or
   external JSONL, not through core assumptions.

2. Turn one-shot runs into explicit research loops.
   A loop should know its phase, state, artifacts, open questions, confidence,
   and next action.

3. Add durable research memory.
   The engine should remember thesis history, source reliability, unresolved
   questions, watchlists, and claim drift between runs.

4. Add verifier and evaluator layers.
   Collection and synthesis should be checked by independent deterministic and
   optional LLM-based evaluators.

5. Support authorized logged-in research without leaking secrets.
   Cookies, session state, and tokens must never be committed. Logged-in
   collectors should use local browser state, local storage-state references, or
   user-provided external evidence.

6. Make the open-source project credible.
   The repo should have a clear architecture, examples, docs, tests, doctor
   commands, and platform support matrix.

## Non-Goals

- Do not build a generic autonomous agent framework.
- Do not bypass paywalls, login walls, robots controls, rate limits, broker
  entitlements, or platform terms.
- Do not store user cookies, API tokens, or private account data in the repo.
- Do not depend on AgentReach or OpenCLI at runtime for the core package.
- Do not make financial trade execution part of Research Engine.
  Market research and decision briefs are in scope. Orders, brokerage access,
  and trading automation are out of scope.

## Target Loop Model

The target Research Engine loop has eight phases.

### 1. Discover

Input sources:

- Watchlist topics.
- X account groups and curated feeds such as `@shrik1645608`.
- GitHub repos and issue searches.
- RSS feeds.
- Official IR/news pages.
- User prompts such as "research this".
- Previous unresolved questions.

Output artifact:

- `discovery_candidates.json`

Each candidate includes topic, source, trigger reason, freshness, estimated
impact, and recommended pack.

### 2. Plan

The planner selects a research pack and builds a scoped plan:

- Topic and intent.
- Claims to test.
- Counterclaims to test.
- Platforms and source tiers.
- Connector route.
- Expected evidence shape.
- Coverage targets.
- Stop criteria.

Output artifact:

- `loop_plan.json`

The existing `query_plan.json` becomes the per-run collection plan inside the
larger loop plan.

### 3. Collect

Collection happens through connectors:

- `web_page` for simple public pages.
- `web_crawler` for sitemap, crawl, and Playwright-rendered public/authorized
  pages.
- `finance_quote` for public quote snapshots.
- `external_jsonl` for authorized evidence exports.
- `agent_reach_bridge` for AgentReach-installed CLIs and compatible upstream
  tools.
- `opencli_bridge` for browser-recorded or adapter-based website workflows.
- `chrome_platform_sampler` for low-volume authorized X, Reddit, LinkedIn,
  Xiaohongshu, and YouTube sampling from the user's local Chrome session.

Output artifacts:

- `collection_execution.json`
- `evidence_raw.jsonl`
- `evidence.jsonl`

The existing `evidence.jsonl` remains the normalized source trace. A new
`evidence_raw.jsonl` is useful for debugging connector transformations.

### 4. Verify

Verification checks:

- Source reliability.
- Freshness.
- Duplicate and syndication relationships.
- Primary-vs-secondary source distinction.
- Contradictions between sources.
- Missing required source categories.
- Claims with weak support.
- Numeric consistency for financial or market claims.
- Connector warnings and partial failures.

Output artifacts:

- `verification_report.json`
- `verification_report.md`

The current `evidence_quality.json` should become one input into the broader
verification report.

### 5. Synthesize

Synthesis produces:

- Claim review.
- Supply/demand or domain-specific matrix.
- Decision brief.
- Research report.
- Citation-ready evidence references.

Output artifacts:

- `claim_review.json`
- `supply_demand_matrix.json`
- `decision_brief.json`
- `research_report.md`

This phase should remain auditable. The LLM may write prose, but evidence rows
and verification artifacts must exist first.

### 6. Reflect

Reflection decides what should happen next:

- Stop because confidence and coverage are sufficient.
- Rerun a deeper collection pass.
- Add a missing source tier.
- Ask the user for login or private source access.
- Add a new claim to test.
- Mark a thesis as unresolved.
- Schedule monitoring.

Output artifact:

- `reflection.json`

Key fields:

- `loop_status`: `complete`, `needs_more_evidence`, `needs_user_input`,
  `monitor`, `failed`.
- `confidence`.
- `coverage_gaps`.
- `follow_up_queries`.
- `recommended_connectors`.
- `user_questions`.
- `next_run_spec`.

### 7. Remember

Memory should be explicit, local, and inspectable.

Memory files:

- `state/thesis_ledger.jsonl`
- `state/source_registry.json`
- `state/watchlists.json`
- `state/open_questions.jsonl`
- `state/claim_history.jsonl`
- `state/connector_capabilities.json`

Memory responsibilities:

- Track thesis changes over time.
- Track which sources are reliable for which domains.
- Track open questions that previous runs could not answer.
- Track connector availability and authentication status.
- Track claim drift when new evidence contradicts older conclusions.

### 8. Monitor

Monitoring turns selected theses into recurring checks.

Examples:

- "Re-check memory cycle thesis after Micron earnings."
- "Monitor SK Hynix ADR listing and institutional flow."
- "Watch @shrik1645608 Loop Engineering feed weekly for new system design
  patterns."
- "Re-run source capability doctor every week."

Output artifacts:

- `monitor_plan.json`
- `monitor_runs.jsonl`

Monitoring should be opt-in and local. The core open-source package can expose
the data model and CLI commands without owning a scheduler.

## Connector Strategy

### AgentReach Bridge

Purpose:

- Use AgentReach as an upstream capability provider.
- Detect and call installed tools such as Twitter/X, Reddit, Xiaohongshu,
  Xueqiu, YouTube, Bilibili, RSS, Jina Reader, GitHub CLI, and web search.

Design:

- Keep `agent_reach_bridge` optional.
- Add `research-engine doctor agentreach`.
- Record per-tool availability in `state/connector_capabilities.json`.
- Normalize stdout from JSON, JSONL, and plain text.
- Never assume AgentReach is installed.

### OpenCLI Bridge

Purpose:

- Use OpenCLI for sites where a user needs repeatable browser workflows, logged
  in sessions, or no stable public API.

Design:

- New connector id: `opencli_bridge`.
- Add command templates and adapter definitions.
- Prefer structured output such as JSON when available.
- Store adapter recipes/config only when they do not include secrets.
- Reference local browser/session state without committing it.

Example source:

```json
{
  "source_id": "x_loop_seed_feed",
  "connector": "opencli_bridge",
  "platform": "x",
  "command": "opencli x search --query \"loop engineering\" --format json",
  "source_kind": "authorized_browser_workflow"
}
```

### Web Crawler Connector

Purpose:

- Reuse the stronger crawler already present in `web-to-podcast`.
- Support seed URLs, sitemap URLs, BFS crawl, include/exclude patterns, static
  fetching, Playwright rendering, scrolls, selectors, and optional storage-state
  references.

Design:

- New connector id: `web_crawler`.
- Port or vendor only the minimal reusable crawler logic.
- Keep browser dependencies optional.
- Emit normalized evidence rows and raw debug metadata.

### Chrome Platform Sampler

Purpose:

- Reuse the logged-in browser sampler from `Agentic Engineer`.
- Support low-volume authorized sampling from X, Reddit, LinkedIn,
  Xiaohongshu, and YouTube.

Design:

- New connector id: `chrome_platform_sampler`.
- Read only visible search results and source links.
- Require explicit user authorization for logged-in account use.
- Do not post, like, follow, message, or mutate account state.
- Do not store cookies or browser profile data.

### External JSONL

Purpose:

- Remain the universal ingestion path for any proprietary or manually exported
  evidence.

Design:

- Keep the current connector.
- Expand docs with more examples.
- Validate required fields and warn on weak rows.

## X Account Group Support

The user-provided `@shrik1645608` feed should become a first-class source type
for loop-engineering research.

Config model:

```json
{
  "id": "loop_engineering_x_group",
  "platform": "x",
  "accounts": ["shrik1645608", "RohOnChain", "svpino"],
  "keywords": [
    "loop engineering",
    "harness engineering",
    "self-learning agent",
    "self-improving agent",
    "agent gets better over time",
    "quant trading system"
  ],
  "capture_modes": ["authorized_chrome", "opencli", "external_jsonl"],
  "max_items": 20
}
```

Expected behavior:

- Search the configured account group and repost feed for seed concepts.
- Extract linked X Articles, threads, media alt text when available, and external
  links.
- Convert each finding into evidence rows.
- Feed extracted concepts into a `loop_engineering` research pack.

## Research Packs

Add a new default pack:

- `loop_engineering`

Pack intent:

- Research and compare loop/harness engineering patterns for agents.

Initial claim specs:

- `loop_requires_state`: strong loops require durable state/memory.
- `harness_beats_prompting`: harness design matters more than prompt text for
  repeated agent performance.
- `verifier_is_core`: independent verification improves reliability.
- `connectors_are_upstream`: broad tool access is useful only when normalized
  into auditable evidence.
- `human_gate_needed`: logged-in, paid, financial, or high-side-effect actions
  need explicit human gates.

Initial matrix nodes:

- Discovery.
- Planning.
- Collection.
- Verification.
- Synthesis.
- Reflection.
- Memory.
- Monitoring.
- Connector capability.
- Evaluation.

## State And Memory Model

### Thesis Ledger

`state/thesis_ledger.jsonl`

Each row:

```json
{
  "thesis_id": "memory-cycle-2026",
  "topic": "DRAM/HBM memory cycle",
  "stance": "supported",
  "confidence": 0.74,
  "latest_run_id": "2026-06-26-dram-hbm-memory-cycle",
  "supporting_claims": ["price_acceleration", "supply_tightness"],
  "open_questions": ["Does NAND demand remain strong at higher prices?"],
  "updated_at": "2026-06-26T00:00:00Z"
}
```

### Source Registry

`state/source_registry.json`

Tracks:

- Source host.
- Platform.
- Source kind.
- Reliability tier.
- Access mode.
- Known limitations.
- Last successful collection.
- Last failure.

### Connector Capabilities

`state/connector_capabilities.json`

Tracks:

- Installed upstream commands.
- Version strings when available.
- Authentication status when safely detectable.
- Last doctor run.
- Supported output formats.
- Warnings.

## Verification And Eval Harness

Add two layers.

### Deterministic Verification

Always runs:

- Required source categories satisfied.
- Evidence freshness.
- Duplicate clustering.
- Contradiction flags.
- Numeric sanity checks.
- URL/source completeness.
- Connector failure and warning review.

### Optional LLM Judge

Runs only after deterministic evidence artifacts exist.

Judge tasks:

- Identify unsupported claims in the report.
- Identify missing counterevidence.
- Check citation alignment.
- Suggest follow-up queries.
- Assign confidence and coverage grades.

The judge output must be stored separately from deterministic artifacts:

- `llm_judge_report.json`
- `llm_judge_report.md`

### Benchmark Cases

Add local eval cases:

- Generic open-web research.
- Memory cycle market research.
- Loop engineering design research.
- Logged-in X seed import via external JSONL.
- AgentReach missing-tools failure mode.
- OpenCLI missing-tools failure mode.
- Conflicting evidence set.
- Duplicate/syndicated evidence set.

The eval command should produce:

- Pass/fail.
- Coverage score.
- Citation quality score.
- Conflict detection score.
- Regression summary.

## CLI Design

Existing command:

```bash
research-engine run "research DRAM HBM supply shortage"
```

New commands:

```bash
research-engine loop "research DRAM HBM supply shortage"
research-engine discover --watchlist state/watchlists.json
research-engine reflect runs/<run_id>
research-engine remember runs/<run_id>
research-engine doctor
research-engine doctor agentreach
research-engine doctor opencli
research-engine doctor chrome
research-engine eval
```

The `run` command remains stable. The `loop` command wraps `run` with
reflection and memory.

## Artifact Layout

One-shot run:

```text
runs/<run_id>/
  run_manifest.json
  query_plan.json
  collection_execution.json
  evidence_raw.jsonl
  evidence.jsonl
  evidence_quality.json
  verification_report.json
  claim_review.json
  supply_demand_matrix.json
  decision_brief.json
  reflection.json
  research_report.md
```

Loop:

```text
loops/<loop_id>/
  loop_manifest.json
  loop_plan.json
  iterations/
    001-<run_id>/
    002-<run_id>/
  final_report.md
```

Persistent state:

```text
state/
  watchlists.json
  thesis_ledger.jsonl
  source_registry.json
  open_questions.jsonl
  claim_history.jsonl
  connector_capabilities.json
```

## Safety And Privacy

Rules:

- No cookie, token, password, browser profile, broker credential, or paywalled
  content cache is committed.
- Logged-in browser collection is read-only by default.
- Any side-effect action requires explicit user authorization and is out of
  scope for the open-source core.
- Financial outputs must remain research briefs, not trade instructions.
- The engine should preserve source links and confidence labels so users can
  inspect evidence before acting.

## Implementation Slices

### Slice 1: Spec And Docs

- Add this design spec.
- Update README positioning.
- Add connector support matrix.
- Document Python 3.10+ test setup clearly.

### Slice 2: Doctor And Capability Registry

- Add `research-engine doctor`.
- Detect Python version, optional package availability, AgentReach tools,
  OpenCLI command, GitHub CLI, yt-dlp, and browser-related optional deps.
- Write `state/connector_capabilities.json`.

### Slice 3: OpenCLI Bridge

- Add `opencli_bridge` connector.
- Add tests for JSON, JSONL, plain text, command missing, command failure, and
  row normalization.
- Add docs for adapter recipes without secrets.

### Slice 4: Web Crawler Connector

- Extract minimal crawler from `web-to-podcast`.
- Support seed URLs, sitemap URLs, crawl config, static fetch, optional
  Playwright rendering, selectors, and storage-state path references.
- Add integration-style tests with local HTML fixtures.

### Slice 5: Chrome Platform Sampler Bridge

- Wrap the existing Chrome sampler as an optional connector.
- Keep it local and read-only.
- Add docs for user authorization and account-state boundaries.

### Slice 6: Loop Runtime

- Add `loop` command.
- Add `reflection.json`.
- Add `loops/<loop_id>` artifact layout.
- Add stop criteria and next-run recommendations.

### Slice 7: Persistent Memory

- Add thesis ledger, source registry, open questions, claim history, and
  connector capabilities.
- Add `remember` command.
- Add drift detection between old and new thesis states.

### Slice 8: Eval Harness

- Add deterministic benchmark fixtures.
- Add `research-engine eval`.
- Add regression metrics for coverage, citation quality, conflict detection,
  and connector failure handling.

## Testing Strategy

Unit tests:

- Pack selection and schema normalization.
- Connector command rendering and output normalization.
- Doctor capability detection.
- Reflection decision rules.
- Memory append/update behavior.
- Verification rules and conflict detection.

Integration tests:

- One-shot generic research dry run.
- Memory cycle pack run with mocked connectors.
- Loop engineering pack run with mocked X/external evidence.
- AgentReach missing-tools warning path.
- OpenCLI missing-command warning path.
- Web crawler local fixture crawl.

End-to-end smoke tests:

- `research-engine run ... --dry-run`
- `research-engine loop ... --dry-run`
- `research-engine doctor`
- `research-engine eval`

Manual authorized tests:

- X seed group capture from `@shrik1645608`.
- Lenny authorized external evidence import.
- LinkedIn authorized browser sampling.

## Acceptance Criteria

The design is implemented when:

- A user can run one command for a research loop and receive auditable artifacts.
- Missing optional tools produce clear warnings, not crashes.
- AgentReach and OpenCLI are optional upstreams, not required core deps.
- Browser/login-based collection remains read-only and local.
- A loop can produce follow-up queries and either stop or schedule monitoring.
- Persistent memory records thesis state and open questions across runs.
- Eval fixtures can catch regressions in evidence quality and contradiction
  handling.
- The GitHub README clearly explains why Research Engine is not "just another
  crawler".

## Open Decisions

Resolved for this spec:

- Research Engine should be an evidence-first loop harness, not a generic agent
  runtime.
- AgentReach and OpenCLI should be optional upstream capability bridges.
- Logged-in X and other platform data should enter through authorized local
  connectors or external JSONL.
- Trading execution is out of scope.

Implementation choices to make during planning:

- Whether loop state should default to `state/` in the project root or a
  user-configured app directory.
- Whether optional browser support should live in the main package extras or a
  companion package.
- Whether the first loop runtime should be deterministic-only or include an
  optional LLM judge behind a flag.
