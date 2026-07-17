# M2 P1 Accuracy and Automatic PDF Reporting Implementation Plan

**Design:** `docs/superpowers/specs/2026-07-16-m2-p1-pdf-reporting-design.md`

## Goal

Ship generic automatic PDF reporting plus focused accuracy fixes without hard-coding the SDE/FDE validation case.

## Steps

1. **Establish the baseline**
   - Run the existing test suite with the bundled ReportLab package available.
   - Record any pre-existing failures before changing runtime code.

2. **Fix the `job_market` profile**
   - Add failing tests for default US scope, old-but-active official postings, and distinct stable job identities.
   - Default missing job-market geography to `US` while preserving explicit geography.
   - Remove publication-age rejection for currently active official postings.
   - Make ATS ID and canonical URL authoritative over content-similarity duplicate flags.

3. **Preserve repair constraints and temporal meaning**
   - Add failing tests that reproduce the validation query losing time, role, and company constraints.
   - Record and preserve deterministic constraint terms during query simplification.
   - Add separate extraction for `updated_at` and `observed_at` while keeping current publication-date behavior compatible.
   - Use the most relevant temporal field for current data-series freshness.

4. **Add the smallest reusable PDF renderer**
   - Declare ReportLab as a runtime dependency.
   - Extract the useful Markdown-to-PDF behavior from the existing one-off script into one `pdf_report.py` module.
   - Render a restrained A4 report with embedded CJK fonts, links, tables, headers, footers, and page numbers.
   - Write atomically and return a serializable status object.

5. **Integrate PDF generation once**
   - Generate PDF after all standard run artifacts and Markdown report exist.
   - Always write `pdf_report_status.json`.
   - Update `run_manifest.json` with PDF status/path after the rendering attempt.
   - Append a non-fatal warning when rendering fails.
   - Surface the PDF path/status through the existing run result and CLI JSON.

6. **Regression and acceptance**
   - Run focused tests after each logical change.
   - Run the full suite without weakening existing gates.
   - Run fixture-based generic, technical, job-market, dry-run, and failed-source cases.
   - Run the live United States SDE/FDE employment-market research with the latest engine.
   - Inspect the Research Engine manifest, evidence, quality, loop, repair, facet, and snapshot artifacts.
   - Render the final PDF to PNG with Poppler and inspect every page.

## Stop Conditions

- Do not replace the existing synthesis layer with PDF-specific analysis.
- Do not add geographic inference beyond the US default.
- Do not accept a fix that makes the job snapshot count discovery snippets or unknown-status rows as active.
- Do not deliver a PDF that was not rendered and visually inspected.
