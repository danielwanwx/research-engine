# Codex Network Execution Design

**Date:** 2026-08-19  
**Status:** Approved for implementation planning

## Problem

Research Engine is sometimes launched by the installed Codex Skill inside an execution sandbox that has no DNS configuration. In that environment every AnySearch request fails with `dns_resolution_failed`, even though the Mac host can resolve and reach `api.anysearch.com`. Retrying connectors cannot restore a DNS service that the process is not permitted to use.

The 2026-08-19 TikTok role run demonstrates the failure: five requests to `api.anysearch.com` exhausted their retries and produced zero evidence rows. Running the same Research Engine checkout outside the restricted sandbox collected 31 rows. Therefore this is an execution-environment failure, not an AnySearch outage, a successful zero-row response, or evidence that no matching roles exist.

## Decision

Fix the Codex Skill execution policy rather than adding connector retries, DNS-over-HTTPS, or an automatic search-provider fallback.

Before a network-backed research run, the Skill must execute a small DNS preflight in the same environment as the planned command. If the preflight cannot resolve the selected search endpoint because the sandbox has no DNS, the agent must rerun the exact read-only Research Engine command with network-enabled execution approval. It must not reinterpret the failure as local-machine DNS failure or as a successful empty research result.

The preflight is diagnostic, not a second network client. It must not collect research evidence, persist credentials, alter accounts, or change the requested topic, pack, source options, output path, or report mode.

## Error Handling

- If DNS fails only in the restricted execution environment and succeeds with network-enabled execution, continue the research run normally.
- If DNS also fails in the network-enabled environment, preserve the connector failure and report it as an actual host/DNS problem.
- If network-enabled execution is not authorized, stop with an explicit infrastructure limitation; do not return a research conclusion.
- If the endpoint resolves but the connector returns HTTP, authentication, rate-limit, robots, or zero-row outcomes, preserve those existing outcome semantics.

## Scope

This change updates:

- the repository Skill at `skills/research-engine/SKILL.md`;
- regression coverage that verifies the Skill's network preflight and rerun policy;
- the installed Skill mirror at `~/.codex/skills/research-engine/SKILL.md` after repository tests pass.

No connector implementation, DNS resolver, provider fallback, report behavior, pack routing, or LoopCoach code is changed.

Existing uncommitted changes in `artifacts.py`, `collection_pipeline.py`, `execution.py`, `runner.py`, and `tests/test_execution.py` are outside this fix and must not be staged, reverted, or included in its commit.

## Verification

1. A regression test confirms the repository Skill requires same-environment DNS preflight and network-enabled rerun of the unchanged command.
2. The existing AnySearch DNS classification tests continue to pass.
3. The full Research Engine test suite and Ruff pass.
4. The installed Skill is byte-identical to the repository Skill.
5. A network-enabled Research Engine smoke run collects evidence successfully.
6. The commit contains only the design, Skill, and directly related regression test; unrelated working-tree changes and user output directories remain untouched.

