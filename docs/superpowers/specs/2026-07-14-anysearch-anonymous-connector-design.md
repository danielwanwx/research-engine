# AnySearch Anonymous Connector Design

## Goal

Give Research Engine a fast, default public-web discovery source so a generic
research run no longer stops with `failed_no_sources`. The connector will use
AnySearch's anonymous `POST /v1/search` API, normalize source URLs and text into
the existing evidence contract, and preserve the engine's quality, duplicate,
conflict, telemetry, and stop checks.

## Constraints

- Anonymous access only. Do not send or read an API key.
- Public research topics only; the query is transmitted to AnySearch.
- Read-only collection. No browser login, posting, account creation, or other
  remote mutation.
- Python standard library only; keep the package dependency-free.
- Preserve existing pack, target-intelligence, external-evidence, AgentReach,
  OpenCLI, GitHub, and explicit web-page behavior.
- Never store response headers, credentials, or opaque account data in run
  artifacts.

## Considered Approaches

### A. Direct REST connector — selected

Add a small `anysearch_search` connector using `urllib.request`. Each pack query
becomes a normal collection request, so the existing executor supplies bounded
concurrency, retry, cache, timeout telemetry, and deterministic artifacts.

Advantages: shortest path, no new runtime dependency, fastest execution, clean
fit with the current connector contract. Trade-off: anonymous quota and rate
limits apply, and result freshness still requires source-level judgment.

### B. Remote MCP bridge

Connect to `https://api.anysearch.com/mcp` and translate MCP tool output.

Advantages: access to the agent-native surface. Trade-off: requires an MCP
client/runtime, adds protocol and configuration complexity, and duplicates the
existing connector abstraction.

### C. Install and invoke the AnySearch skill/CLI

Install AnySearch's external skill and execute its scripts as a bridge.

Advantages: reuses vendor tooling. Trade-off: adds installation state, multiple
language runtimes, and command-safety concerns for a single HTTP endpoint.

Approach A is the minimal solution that solves the current `generic` pack
failure.

## Architecture

### Connector

Create `research_engine.connectors.anysearch.AnySearchSearchConnector` with
connector ID `anysearch_search`.

Input source fields:

- `query`: required search text;
- `zone`, `language`, `tag`, and `params`: optional pass-through fields for
  future pack-specific use, omitted by the default generic path;
- request `max_results`: clamped to AnySearch's documented 1–20 range.

The transport sends JSON to `https://api.anysearch.com/v1/search` without an
`Authorization` header. A successful response is valid only when it is an
object containing `code == 0` and `data.results` as a list.

Each result becomes one evidence row containing:

- original `title`, `url`, `snippet`, and cleaned `content`;
- `text` chosen from `content`, then `snippet`;
- `source_kind=anysearch_result`;
- `source_class=discovery_result`;
- `access_mode=public_anysearch_anonymous`;
- query, capture time, publisher hostname, and source confidence;
- result-level search latency and total-result metadata where available.

Rows with neither a public HTTP(S) URL nor useful text are dropped. Output text
is bounded to the same scale as other connectors.

### Routing

AnySearch is enabled by default for ordinary non-target research. A
`--no-anysearch` CLI flag provides an explicit privacy/quota opt-out.

Research depth controls query breadth:

- `quick`: first pack query only;
- `deep` and `audit`: up to three pack queries.

Each query is a separate collection request. The existing executor runs them
concurrently and records each request independently. Structured target runs
keep their current official/xAI discovery path and do not add AnySearch by
default.

The query plan records `collection_modes.anysearch`, source IDs, and anonymous
access mode so downstream consumers can audit how evidence was obtained.

## Error Handling and Loop Feedback

- Invalid local configuration or malformed successful response: return no rows
  with a sanitized warning.
- Anonymous quota, rate limit, or other HTTP error: surface only status/type;
  never persist headers or any credentials returned by an upstream error body.
- Network/timeout/server failure: let the existing executor apply its bounded
  retry and timeout policy, then record the failure.
- Some queries succeed and others fail: retain successful evidence and finish
  `complete_with_warnings`.
- All queries fail or return no usable rows: preserve the existing
  `failed_no_rows` and `sources_returned_no_evidence` stop behavior.

## Verification

Add focused tests for:

1. anonymous requests contain no `Authorization` header;
2. request limits are clamped and optional fields are passed safely;
3. successful results normalize into evidence rows;
4. malformed payloads and API error codes return sanitized warnings;
5. default generic runs plan AnySearch sources, while `--no-anysearch` and
   structured target runs do not;
6. query-plan artifacts record AnySearch mode and existing injected-connector
   tests remain stable.

Run `python -m pytest -q` and `python -m ruff check src tests` before commit.

## Acceptance

- `research-engine run "<generic topic>" --pack auto` has executable sources
  without extra flags or credentials.
- The run writes normalized AnySearch evidence and all existing quality/loop
  artifacts.
- No API key is sent, read, or stored.
- Existing tests pass, new connector/routing tests pass, and documentation
  clearly identifies the third-party anonymous query boundary.

## Non-goals

- Installing the AnySearch skill or MCP server.
- Authenticated/paid quota support.
- A general-purpose crawler or automatic recursive page fetch.
- Treating AnySearch's self-reported benchmark claims as independent evidence.
