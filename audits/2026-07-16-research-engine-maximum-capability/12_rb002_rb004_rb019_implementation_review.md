# RB-002 / RB-003 / RB-004 / RB-019 Implementation Review

## Outcome

Fable final verdict: **approve**. No unresolved P0-P2 findings.

## Implemented

- Repeated and concurrent runs atomically reserve immutable directories using the
  existing readable run id followed by `--02`, `--03`, and later suffixes.
- Normalization assigns unique run-scoped evidence ids while retaining imported ids
  as `source_evidence_id`; quality reporting separates id collisions from content
  deduplication.
- Invalid and discovery-only rows cannot ground claims, matrices, or conflicts,
  including platform search pages and structured-target discovery rows.
- Distinct opposing cited evidence calibrates supported conclusions to `conflicted`
  with confidence capped at `medium`; self-conflicting rows do not calibrate alone.
- Research CLI invocations append success and failure records to `journal.jsonl`.
  Success output is emitted only after the journal write succeeds.
- Journal argv and error fields redact compound assignments, embedded authorization
  credentials, split sensitive flags, and compound sensitive flags without masking
  ordinary authorization prose.

## Review loop

1. Initial Fable review found a structured-target discovery bypass, compound-key
   secret leakage, success output preceding the journal write, and a compatibility
   regression in `unique_evidence_count` semantics.
2. Second review confirmed those repairs and found an assignment-regex overlap plus
   embedded Basic authorization leakage.
3. Third review confirmed the credential fix and found overbroad masking of ordinary
   insurance and payment authorization prose.
4. The live final round found an adjacent split-flag match beginning inside the
   preceding assignment value.
5. Final review verified the boundary-aware compound-flag repair and the complete
   batch. Verdict: approve with no findings.

## Verification

- Python 3.10: 160 tests passed.
- Ruff: all checks passed.
- Offline eval: 9/9 checks; 5/5 invalid probes detected.
- Sequential smoke: base and `--02` directories, unchanged first-run bundle, two
  matching journal records, and no tested secret leakage.
- Concurrent reservation smoke: 64/64 unique directories.
- `git diff --check`: passed.

## Residual risk

Secret redaction is deterministic heuristic logic, so future real credential shapes
should be added as regression fixtures. Journal rotation and retention are deferred.
Independent-domain and polarity-aware conflict analysis remains RB-015.
