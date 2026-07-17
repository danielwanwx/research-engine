# M0 Run Durability and Claim Integrity Design

**Date:** 2026-07-16

**Scope:** RB-002, RB-003, RB-004, and RB-019

**Status:** Implemented; independently reviewed and approved

## Goal

Make every research run durable and traceable, make every evidence citation
unambiguous, and prevent discovery-page echoes or unresolved opposing evidence
from producing confident supported conclusions.

This batch completes the remaining Trust & Measurement work after RB-001 and
RB-010. It must preserve the zero-dependency core and the existing first-run
directory names and public result fields.

## Inputs and Constraints

- Use the current uncommitted RB-001/RB-010 implementation as the baseline.
- Preserve unrelated and pre-existing dirty-worktree changes.
- Use only Python's standard library and existing project helpers.
- Keep the first run id as `<date>-<slug>` for compatibility.
- Do not delete, replace, or mutate an earlier run bundle.
- Keep imported evidence identifiers as provenance metadata, not primary keys.
- Keep search result pages available as observable discovery artifacts, but do
  not allow them to ground claims, matrices, or conflict chains.
- Journal only research `run` CLI invocations in this batch. Programmatic
  library calls and `doctor` invocations are outside RB-019's acceptance test.

## Approaches Considered

### 1. Atomic sequential suffixes — selected

Reserve `<date>-<slug>` with an atomic directory creation. If it exists, try
`<date>-<slug>--02`, then `--03`, and so on. Assign fresh run-scoped evidence
ids, preserve source ids as metadata, apply deterministic claim eligibility,
and append one machine-written journal entry per CLI run.

This keeps human-readable paths, supports unattended reruns, is safe against
concurrent directory reservation, and needs no new dependency or service.

### 2. Refuse collisions unless the user chooses another id

This gives the caller explicit control but turns routine scheduled or repair
runs into failures and adds CLI policy surface. It does not satisfy the desired
unattended rerun behavior as well as sequential suffixes.

### 3. UUID or content-addressed run storage

This provides globally unique identifiers and could support a future event
store, but it breaks readable run paths and introduces migration and indexing
work that RB-002 does not require.

## Architecture

The implementation stays in existing boundaries:

1. `runner.py` owns run-directory reservation and run-scoped evidence ids.
2. `quality.py` owns the distinction between content-valid evidence and
   claim-eligible evidence, plus evidence-id collision observability.
3. `synthesis.py` owns conflict-aware stance and confidence calibration.
4. `artifacts.py` provides one append-only JSONL primitive using a single
   `O_APPEND` write.
5. `cli.py` records the completed or failed research invocation with existing
   command redaction.

No repository, event-store, schema framework, locking library, or new service
is introduced.

## RB-002: Immutable Run Directories

Before collection begins, the runner creates the output root and atomically
reserves a run directory with `mkdir(exist_ok=False)`:

- first attempt: `<date>-<slug>`;
- later attempts: `<date>-<slug>--02`, `--03`, and so on;
- the returned `ResearchRunResult.run_id` and `run_dir` use the reserved name;
- `run_manifest.json.run_id` uses the same reserved name.

Atomic reservation avoids the check-then-create race between concurrent runs.
If a fatal error happens after reservation, the directory remains as evidence
that an attempt occurred; the CLI journal records the failed invocation even
if no completed result was returned to identify that directory. Earlier
directories are never cleaned up or reused automatically.

## RB-003: Run-Scoped Evidence Identity

`normalize_rows` assigns every collected row a fresh sequential id in final
row order: `ev-0001`, `ev-0002`, and so on. A non-empty incoming
`evidence_id` is retained as `source_evidence_id`; an existing
`source_evidence_id` is not overwritten.

The quality report records:

- `unique_evidence_id_count`;
- `evidence_id_collision_count`;
- a warning if rows passed directly into the quality layer still contain a
  collision.

The existing `unique_evidence_count` keeps its content-deduplication meaning;
ID uniqueness uses the new fields so existing consumers do not silently change
semantics.

The runner must produce zero collisions. The quality-layer check remains as a
guard for library callers and future connector regressions.

## RB-004: Claim Eligibility and Conflict Calibration

Content validity and claim eligibility are separate predicates:

- `is_evidence_eligible` continues to mean the fetched content is usable;
- `is_claim_eligible` additionally rejects discovery-only rows identified by
  platform source kind/id, `source_class == "discovery_only"`, or a structured
  target `claim_fitness.disposition` other than `accepted`.

Claims, supply/demand matrix nodes, and conflict matching use
`is_claim_eligible`. Discovery rows remain in `evidence.jsonl` and quality
reports for observability.

When raw rows exist but none are claim-eligible, pack-specific claims use the
verdict `insufficient_valid_evidence`. They do not contribute to a supported
or partially supported stance.

The runner passes deterministic conflict flags into claim synthesis. A conflict
can change the conclusion only when:

1. at least one claim citation overlaps the flag; and
2. the flag has at least one distinct claim-eligible support id and one
   distinct claim-eligible opposition id.

For such a conflict, a supported or partially supported overall stance becomes
`conflicted`, confidence is capped at `medium`, and the overlapping flag ids
are recorded in the claim review. A row appearing on both sides by itself does
not qualify. Full polarity scoring and independent-domain chains remain RB-015.

`decision_brief.json` inherits the calibrated stance and uses the existing
safe fallback action bias `analyze_before_action` when the pack has no explicit
`conflicted` mapping.

## RB-019: Append-Only CLI Invocation Journal

Each parsed research `run` CLI invocation appends one JSON object to
`<output>/journal.jsonl`. The schema is `invocation_journal.v1` and contains:

- redacted `argv`, using the existing `redact_command` helper;
- `started_at` and `ended_at` machine timestamps;
- integer `exit_status`;
- actual `run_id` and `run_dir` after a result is returned; these are `null`
  when the engine fails before returning its result;
- engine `run_status` on success;
- redacted error type and message on failure.

Redaction covers compound sensitive assignment keys such as `client_secret`
and `aws_secret_access_key`, plus embedded known Authorization credential
schemes, while preserving ordinary insurance, payment, and prior-authorization
prose.

The append helper creates the parent directory and performs one encoded-line
write through `O_APPEND`. Journal write failure is surfaced as a CLI error; it
is never silently ignored, and no success JSON is printed until the success
journal entry is durable. Size-based rotation is deferred until journal growth
is measured because rotation would weaken the simple append-only contract.

## Data Flow

```text
CLI parse
  -> capture redacted argv + start time
  -> atomically reserve unique run directory
  -> collect and normalize rows with fresh run-scoped ids
  -> retain imported ids as source_evidence_id
  -> score content validity and claim eligibility
  -> build discovery-free claims, matrix, and conflict flags
  -> calibrate stance/confidence against usable conflicts
  -> write immutable run bundle
  -> append success/failure invocation record
  -> return actual run_id and run_dir
```

## Error Handling

- Existing run directory: allocate the next suffix; do not mutate the existing
  directory.
- Output path is not writable or is a file: fail before collection.
- Imported id collision: normalize to unique run ids and retain every original
  id in `source_evidence_id`.
- Direct quality-layer collision: report and warn; do not claim uniqueness.
- Only discovery pages or invalid evidence: abstain with insufficient evidence.
- Usable opposing chains: emit `conflicted` and cap confidence.
- Engine exception after CLI parsing: append a failed journal entry and re-raise
  the original exception.
- Journal append failure: report the journal failure and return a non-zero CLI
  exit rather than presenting an unjournaled success.

## Verification

Unit and integration tests will prove:

1. two identical sequential runs create two directories and the first bundle's
   bytes remain unchanged;
2. concurrent-style reservation against an existing directory chooses the next
   suffix without overwrite;
3. mixed connector rows with duplicate imported ids receive unique run ids and
   preserve their source ids;
4. quality reports detect collisions when normalization is bypassed;
5. valid platform search pages remain observable but cannot support claims,
   matrix nodes, or conflict flags;
6. invalid-only or discovery-only rows yield
   `insufficient_valid_evidence` rather than supported claims;
7. distinct opposing cited evidence produces `conflicted` with confidence no
   higher than `medium`;
8. a single self-conflicting row does not trigger the calibrated stance;
9. two successful CLI runs append two ordered journal lines with actual
   distinct run dirs;
10. sensitive split flags and embedded secret assignments are redacted from
    the journal;
11. a failed engine invocation writes a non-zero journal record;
12. a journal append failure emits no success payload;
13. non-credential authorization prose remains unchanged;
14. the full unit suite, Ruff, `make eval`, and a local repeated-run smoke pass.

## Loop Contract

**Goal:** Complete RB-002, RB-003, RB-004, and RB-019 without regressions or
unrelated worktree changes.

**Input scope:** The current repository, the 2026-07-16 audit backlog and B1,
B3, B4, B7, B8 fixtures, plus the existing RB-001/RB-010 implementation.

**Execute:** Implement one shared guard at each existing boundary, add focused
tests, run checks, run a repeated-run smoke test, then submit the complete diff
and artifacts to Fable for independent review.

**Checks:** Targeted tests, full tests, Ruff, offline eval, diff check, immutable
first-run hash comparison, unique evidence ids, conflict calibration, and
journal redaction.

**Feedback rules:** A failing test leads to a root-cause repair in the shared
boundary and a rerun. A Fable correctness or security finding leads to a patch
and another review round. A scope-expanding recommendation is recorded for the
backlog rather than implemented in this batch.

**Records:** This design, test output, eval scorecard, smoke-run directories,
invocation journal, and a Fable review report under the existing audit folder.

**Stop conditions:** Success requires all checks passing and Fable approval
with no unresolved P0/P1 findings. Stop and ask the user if a required fix
would delete prior artifacts, change an unrelated dirty file substantially, add
a dependency, or expand beyond these four backlog items.

## Acceptance

- Same-command reruns always produce distinct run directories.
- Existing run bundles remain byte-for-byte unchanged.
- Every final evidence id is unique within a run and imported ids remain
  traceable.
- Discovery-only and invalid evidence cannot support claims or conflicts.
- Usable opposing cited evidence prevents a high-confidence supported result.
- Every parsed research CLI run produces a redacted, machine-timestamped
  journal line.
- Existing tests and the offline RB-010 evaluation remain green.
- Fable independently approves the implementation with no unresolved P0/P1
  findings.

## Non-Goals

- Run deletion, retention, rotation, or garbage collection.
- User-selectable overwrite or `--force` behavior.
- UUID/content-addressed storage, replay, or run diff tooling.
- Full claim entailment or LLM judging.
- Independent-domain conflict chains or dominant-polarity scoring (RB-015).
- Journaling programmatic library calls or non-run CLI commands.
- New dependencies or broad refactoring.
