---
name: research-engine
description: Use when the user asks to research, investigate, query, verify claims, gather evidence, compare products/companies/markets, monitor a topic, or pull real data from web/platform/forum/news/finance/GitHub-style sources. Route source-grounded research through Research Engine, especially for prompts like research, investigate, 调研, 查询, 深挖, 全网数据, 竞品分析, 市场判断, 投资研究, or claims that need citations and evidence quality checks.
---

# Research Engine

Research Engine is an evidence runtime for agents. Use its bounded summary
contract by default; do not generate a long report unless the user requests
one. From the active repository checkout, read the current artifact and
connector state contract at `docs/artifact-contract.md`.

## Execution Defaults

Start research directly when the topic and requested outcome are clear. Infer
scope and source mix from the request and use balanced `deep` research by
default. Ask a question only when a missing choice would materially change the
result or when login, private data, paid access, credentials, or a destructive
action requires explicit user authorization.

## Workflow

Use Research Engine before ad hoc browsing when the task needs evidence
collection, source coverage, citations, contradiction checks, or reusable
research artifacts.

1. Run the module from the active Research Engine checkout so the skill uses
   the current source tree, including uncommitted fixes. Do not invoke globally installed
   `research-engine` or `research` entry points; they may resolve to an older
   installed package.
2. Use this command for normal agent-driven research:

```bash
cd "$(git rev-parse --show-toplevel)"
PYTHONPATH=src python3 -m research_engine.cli \
  run "<topic>" --pack auto --depth deep --report-mode summary --output runs
```

3. Before a network-backed run, preflight the selected search host in the same
   execution environment as the planned command. For the default AnySearch
   provider, use:

```bash
/opt/homebrew/opt/python@3.10/bin/python3.10 -c \
  'import socket; socket.getaddrinfo("api.anysearch.com", 443)'
```

   If this fails because the sandbox has no DNS configuration, rerun the exact
   same Research Engine command using network-enabled execution approval (for
   Codex shell tools, request the network/sandbox escalation on that command).
   Do not change the topic, pack, flags, output path, or report mode during the
   rerun. If network-enabled execution is not authorized, stop and report the
   infrastructure limitation. Do not interpret sandbox DNS failure as a local
   machine DNS fault, an AnySearch successful zero-row response, or evidence
   about the research topic.
4. The default `--report-mode summary` writes the concise, machine-readable
   `research_summary.json` and skips human-facing documents. Pass
   `--report-mode full` only when the user explicitly requests a report,
   article, long-form analysis, Markdown document, or PDF. Add advanced flags such as `--scope-file`, `--external-evidence`,
   `--browser-auth`, or an explicit `--pack` only when the request requires
   them. Keep `--pack auto` for ordinary company, role, business, and market
   research; do not force `interview_prep` without explicit interview intent.
5. Before a run, verify the module path when there is any doubt:

```bash
PYTHONPATH=src python3 -c \
  'import research_engine; print(research_engine.__file__)'
```

   It must resolve under the active checkout's `src/` directory.
6. Read `research_summary.json` first. Inspect `evidence.jsonl`,
   `evidence_quality.json`, claim and loop artifacts only when the summary is
   incomplete, contested, or the user requires citation verification. Read
   `run_manifest.json`, `query_plan.json`, and `loop_contract.json` when the
   run needs audit/debug context.
7. Keep connector execution and research conclusions separate. In
   `collection_execution.json`, inspect the operational request `status`
   (`ok`, `warning`, `failed`, `retry_exhausted`, `rate_limit`, `robots_denied`,
   `timeout`, `cache_hit`, or `blocked`), `row_count`, and optional `failure_reason`
   (`dns_resolution_failed`, `network_timeout`, `network_unavailable`, or
   `tls_failure`). A shared DNS circuit uses `blocked` with
   `infrastructure_unavailable`; inspect `network_diagnostics` for affected
   hosts and the detection basis. A failed connector is not evidence that the requested
   phenomenon does not exist. A claim-level `insufficient_evidence` verdict and
   a run-level `failed_no_rows` status must remain distinct from connector
   execution outcomes.

## Optional Jev Advisory Triage

Use `jev-triage` only when the user explicitly authorizes its TypeSafe request
with `--allow-jev`, and only over current public evidence:

```bash
PYTHONPATH=src python3 -m research_engine.cli jev-triage \
  --topic "<topic>" --allow-jev --evidence runs/<run-id>/evidence.jsonl
```

It reads at most 32 rows or 128 KiB, then sends the first eight eligible
allowlisted public rows in one batch with one Noul relevance judgment per row.
It returns typed answers, actual provider usage, measured events, and skipped
counts; remaining rows are not reviewed, so supply a bounded next batch as
needed without altering canonical evidence. It is advisory only: it never
fetches or verifies sources and never modifies, drops, or excludes canonical
evidence. Browser, external, bridge, private, and unknown access modes are
rejected before a request.

Resolve credentials from `TYPESAFE_API_KEY`, the optional local macOS Keychain
service `typesafe-ai-jev`, or `--prompt-key` for masked current-process-only
entry. Never ask for a key in chat, a command argument, or an evidence file.
`--allow-jev` records existing authorization for this invocation; it does not
solicit or infer authorization. When configured, authorized, and useful, make
one request for the selected batch and reuse its returned judgment.

## Source Rules

- Prefer the engine's public connectors, configured packs, JSONL external
  evidence bridge, AgentReach bridge, and OpenCLI bridge over one-off scraping.
- Do not ask the user to paste cookies, passwords, API keys, session tokens, or
  private credentials into the chat.
- If login-gated sources are required, ask the user to log in through Chrome or
  export read-only evidence to JSONL, then pass that JSONL to the wizard or
  advanced CLI.
- Treat paywalled or logged-in content as unavailable unless the user has
  authorized access and provides a compliant read-only export.
- Keep source acquisition read-only. Do not post, message, trade, purchase, or
  mutate remote accounts.

## Loop Discipline

- Keep the context clean: rely on artifact files for large evidence and
  summarize only the relevant findings.
- Use focused tools: Research Engine for collection and quality checks;
  browser/Chrome only for login-gated review or targeted verification.
- Stop for real reasons: no configured source, no rows, failed checks, max
  iterations, timeout, or explicit user gate.
- Separate maker and checker: inspect evidence quality, duplicate pressure,
  source warnings, conflict flags, and claim grounding before giving conclusions.

## Output Expectations

When answering the user, include:

- What the engine actually collected and from which source classes.
- Key evidence-backed findings with citations or artifact references.
- Contradictions, weak signals, missing source coverage, and confidence level.
- Practical judgment only after separating facts, inference, and uncertainty.
- The exact artifacts or run directory used for traceability.
