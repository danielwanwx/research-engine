# B8 — Mixed formats (authorized JSONL + PDF + HTML table)

- Command: `... run "mixed format evidence handling audit" --pack b8_mixed --pack-dir <audit>/fixtures/packs --external-evidence tests/fixtures/stripe_false_positive_evidence.jsonl --depth deep --source-timeout-seconds 30` (0.6s)
- Run dir: `runs/2026-07-16-mixed-format-evidence-handling-audit`
- Inputs: pre-existing repo fixture (read-only) + 2 public URLs. No new permissions.

## Findings
1. **evidence_id collision / provenance break**: evidence.jsonl contains TWO ev-0001 and TWO ev-0002. Cause: normalize_rows (runner.py:652) keeps pre-existing evidence_id from external JSONL rows and only generates ids for rows lacking them — no uniqueness enforcement across sources. Any claim citing "ev-0001" is ambiguous. Stable-ID contract broken by the engine's own import path.
2. **PDF**: raw binary again stored as text, tier high (same as B6 — reproduced).
3. **HTML table**: Wikipedia GDP table flattened to linear prose and truncated at 4000 chars — no structure, most of the table gone; tier high.
4. **JSONL import fidelity**: 8 fixture rows imported with titles/urls/confidence preserved — the import path itself works, and is sanitization-aware.
5. **"404: Not Found" rows rated HIGH tier**: three fixture rows whose entire text is `404: Not Found` (14 chars) scored ≥0.72 (self-declared high confidence +0.15, https, title bonuses; missing-text penalty needs *empty* text). Junk detection defeated by 14 characters.
6. Status "complete", zero warnings.

## Rubric
Extraction 1 (PDF 0, table 1, JSONL 4) · Claim-citation 1 (ambiguous ids) · Failure transparency 1 (404-text rows, no warnings) · Artifacts 4 (bundle complete but ids collide) · Latency 5.
Headline per plan rubric: **1/5** (degraded silently on 2 of 3 formats + id integrity bug).
