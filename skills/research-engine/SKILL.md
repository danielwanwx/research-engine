---
name: research-engine
description: Use when the user asks to research, investigate, query, verify claims, gather evidence, compare products/companies/markets, monitor a topic, or pull real data from web/platform/forum/news/finance/GitHub-style sources. Route source-grounded research through Research Engine, especially for prompts like research, investigate, 调研, 查询, 深挖, 全网数据, 竞品分析, 市场判断, 投资研究, or claims that need citations and evidence quality checks.
---

# Research Engine

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

1. Treat `/Users/danielwan/Project/research-engine` as the canonical checkout.
   Run the module from that checkout so the skill always uses the current source
   tree, including uncommitted fixes. Do not invoke the globally installed
   `research-engine` or `research` entry points; they may resolve to an older
   installed package.
2. Use this command for normal agent-driven research:

```bash
cd /Users/danielwan/Project/research-engine
PYTHONPATH=src /opt/homebrew/opt/python@3.10/bin/python3.10 -m research_engine.cli \
  run "<topic>" --pack auto --depth deep --output runs
```

3. Add advanced flags such as `--scope-file`, `--external-evidence`,
   `--browser-auth`, or an explicit `--pack` only when the request requires
   them. Keep `--pack auto` for ordinary company, role, business, and market
   research; do not force `interview_prep` without explicit interview intent.
4. Before a run, verify the module path when there is any doubt:

```bash
PYTHONPATH=src /opt/homebrew/opt/python@3.10/bin/python3.10 -c \
  'import research_engine; print(research_engine.__file__)'
```

   It must resolve under `/Users/danielwan/Project/research-engine/src`.
5. Read `run_manifest.json`, `query_plan.json`, `evidence.jsonl`, `evidence_quality.json`,
   `loop_contract.json`, and `loop_record.json` before summarizing results to
   the user.

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
