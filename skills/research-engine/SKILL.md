---
name: research-engine
description: Use when the user asks to research, investigate, query, verify claims, gather evidence, compare products/companies/markets, monitor a topic, or pull real data from web/platform/forum/news/finance/GitHub-style sources. Route source-grounded research through Research Engine, especially for prompts like research, investigate, 调研, 查询, 深挖, 全网数据, 竞品分析, 市场判断, 投资研究, or claims that need citations and evidence quality checks.
---

# Research Engine

## Mandatory Option Gate

Before running any collection, search, browser, Chrome, connector, or Research
Engine command, present the user with an option gate and wait for their choice.
Do this even when the topic is already clear.

Preferred behavior:

- Use the bundled browser option companion, the same interaction pattern as
  Superpowers Brainstorming: start a local server, push a clickable option
  screen, open it for the user, wait for the `run:start` browser event, then
  continue automatically.
- Use `request_user_input` only when the host explicitly provides it and the
  user asks for native Codex choices instead of the browser companion.
- Use plain text choices only if browser/server startup fails.
- Do not ask the user to re-enter the topic when it is already present in the
  request. Only ask for execution choices.
- After the user chooses, proceed with the selected defaults without asking for
  more input unless credentials, login, or destructive actions would be needed.
- Never silently choose sources and start collecting.

Default option gate:

1. Scope:
   - `us`: United States / North America focus
   - `global`: global English market
   - `compare`: cross-market comparison
2. Sources:
   - `public`: official/public sources only
   - `public_community`: public sources plus forums/social/open-source signals
   - `logged_in`: include authorized logged-in browser exports when available
3. Depth:
   - `quick`: fast scan
   - `deep`: recommended balanced research
   - `audit`: stricter evidence review

## Browser Option Companion

Use the scripts in this skill directory. Resolve `<skill_dir>` to the directory
containing this `SKILL.md`.

1. Start the companion server:

```bash
<skill_dir>/scripts/start-server.sh --project-dir <research-engine-checkout> --foreground
```

The command prints JSON with `url`, `screen_dir`, and `state_dir`. In Codex,
keep this foreground command running as the active companion session until the
selection is read, then stop it with `scripts/stop-server.sh <session_dir>`.
Use `--background` only in shells that preserve background processes after the
tool call exits.

2. Push the option screen:

```bash
node <skill_dir>/scripts/write-options-screen.mjs \
  --screen-dir <screen_dir> \
  --topic "<topic from the user request>"
```

3. Open `url` for the user with the browser/in-app-browser/Chrome tool when
   available. If no browser tool is available, print the URL and ask the user to
   open it. The user should only need to click options and `Start research`.

4. Wait for the browser selection event:

```bash
node <skill_dir>/scripts/read-options-selection.mjs \
  --state-dir <state_dir> \
  --wait-ms 240000
```

The script returns JSON such as:

```json
{"scope":"us","sources":"public_community","depth":"deep","ready":true}
```

If `timed_out` is true or `ready` is false, do not start collection. Ask the
user whether to retry the companion or fall back to text choices.

## Workflow

Use Research Engine before ad hoc browsing when the task needs evidence
collection, source coverage, citations, contradiction checks, or reusable
research artifacts.

1. Locate the Research Engine checkout or installed package.
2. Complete the mandatory browser option gate above.
3. For normal terminal use, run the interactive entry:

```bash
research
research "调研 <topic>"
```

4. Let the wizard ask for any missing terminal-only details, optional JSONL
   evidence exports, and final read-only confirmation.
5. For automation, tests, or explicit advanced requests, use:

```bash
research-engine run "<topic>" --pack auto --output runs
```

6. Read `run_manifest.json`, `evidence.jsonl`, `evidence_quality.json`,
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
