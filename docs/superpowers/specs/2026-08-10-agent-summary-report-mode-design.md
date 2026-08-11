# Agent Summary Report Mode Design

## Goal

Make Research Engine return a concise, machine-readable conclusion by default while preserving
the evidence and quality artifacts needed for verification. Generate the human-facing Markdown
and PDF report only when the caller explicitly requests a full report.

## User Experience

Add `--report-mode summary|full` to `research-engine run` and a matching `report_mode` argument
to `ResearchEngine.run`. The default is `summary`.

- `summary`: write `research_summary.json`; do not write `research_report.md`,
  `research_report.pdf`, or `pdf_report_status.json`.
- `full`: write `research_summary.json` and preserve the current Markdown and PDF behavior.

Skipping document generation in summary mode is successful behavior. It must not add a warning
or lower the run status.

## Summary Contract

`research_summary.json` uses schema `research_summary.v1` and contains only the material an agent
normally needs to answer the user:

- run ID, topic, pack, profile, status, and as-of date;
- headline, stance, confidence, and action bias;
- concise rationale;
- evidence-quality and scope-coverage warnings;
- a bounded list of key evidence references containing evidence ID, title, URL, and quality tier;
- loop status and stop reason.

The summary is derived from the already-produced decision brief, claim review, quality report,
loop record, and evidence rows. It does not run another model or duplicate research work.

## Artifact Policy

Both modes retain the existing machine-readable evidence and audit artifacts, including the run
manifest, query plan, collection execution, evidence JSONL, evidence quality, claim review,
decision brief, and loop records. These files support citation verification and debugging without
forcing the agent to read them on every successful run.

The run manifest records `report_mode` and a `report` object. In summary mode the document status
is `not_requested`; in full mode it records Markdown and PDF results. `ResearchRunResult` keeps its
existing PDF fields for compatibility and reports an empty path plus `not_requested` in summary
mode.

## Skill Behavior

Update the bundled and installed Research Engine Skill to:

1. use the latest source checkout as already configured;
2. read `research_summary.json` first;
3. inspect evidence and quality artifacts only when the summary is incomplete, contested, or
   requires citation verification;
4. pass `--report-mode full` only for explicit requests for a report, article, long-form analysis,
   Markdown document, or PDF.

## Error Handling

Summary serialization is part of the normal artifact contract and should fail visibly if it cannot
be written. Full-report PDF failure retains the existing warning behavior. Summary mode never calls
the PDF renderer, so PDF dependencies cannot affect an ordinary agent research run.

## Testing

Add regression coverage proving that:

- default CLI and Python runs create `research_summary.json` and no Markdown or PDF report;
- summary content includes the conclusion, confidence, warnings, and bounded evidence references;
- `--report-mode full` preserves Markdown and PDF generation;
- invalid report modes are rejected;
- skipped PDF generation produces `not_requested` without warnings or status degradation;
- the Skill invokes summary mode by default and documents the explicit full-report trigger.

Run the complete test suite and lint checks before publishing the implementation.
