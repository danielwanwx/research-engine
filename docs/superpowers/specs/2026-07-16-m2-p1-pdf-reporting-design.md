# M2 P1 Accuracy and Automatic PDF Reporting Design

**Date:** 2026-07-16  
**Status:** approved for planning  
**Scope:** generic Research Engine improvements plus isolated `job_market` accuracy fixes

## 1. Goal

Make every Research Engine run produce a directly usable, standardized PDF report while fixing the highest-impact accuracy defects revealed by the United States SDE/FDE job-market validation.

The implementation must improve reusable engine behavior. It must not hard-code FDE, the validation company list, the validation topic, or conclusions from the employment-market report.

## 2. Non-goals

- Do not build a historical job-posting warehouse or longitudinal snapshot service.
- Do not add complex geographic inference.
- Do not redesign the evidence or claim schemas beyond the fields needed for time metadata and PDF status.
- Do not add a browser, Pandoc, LaTeX, or an HTML rendering stack.
- Do not make PDF generation a second synthesis system.
- Do not change research conclusions merely to make reports look more decisive.

## 3. Architecture

The research pipeline remains the source of truth:

```text
collection -> quality checks -> synthesis -> research_report.md
                                            |
                                            v
                                    research_report.pdf
                                            |
                                            v
                              manifest + pdf status record
```

A small PDF renderer reads the run's already-generated artifacts. It does not recollect evidence or create new conclusions. The Markdown, JSON, and JSONL artifacts remain the auditable data layer; the PDF is the presentation layer.

Each terminal run directory contains:

- `research_report.md`
- `research_report.pdf`
- `pdf_report_status.json`

`run_manifest.json` records the PDF artifact path and a `generated` or `failed` status. PDF generation is attempted for successful, warning, insufficient-evidence, failed-no-source, and dry-run terminal states.

PDF failure is non-fatal to the research result. It must be explicit in the manifest, status artifact, CLI output, and warnings.

## 4. Reusable Core Improvements

### 4.1 Constraint-preserving repair

Repair may simplify noisy wording but must retain hard constraints from the original plan:

- time or as-of bounds;
- role or subject terms;
- company or entity terms;
- explicit comparison targets;
- source restrictions required by the facet.

The repair artifact records the inherited constraints so the behavior remains auditable. A repair that cannot retain required constraints is skipped and recorded rather than converted into a broad unrelated query.

### 4.2 Time metadata

Time extraction distinguishes three meanings:

- `published_at`: when a document or posting was originally published;
- `updated_at`: when the page or dataset was updated;
- `observed_at`: the latest dated observation represented by a data series.

For HTML and structured data pages, extraction may use explicit metadata, visible update labels, table dates, and existing structured fields. Freshness logic uses the field appropriate to the evidence type and does not silently reinterpret one field as another.

This enables current data pages such as FRED series to satisfy current-evidence requirements when the underlying observations are current, even when the page lacks a conventional article publication date.

### 4.3 Automatic PDF output

The renderer uses ReportLab, an already-available dependency, and a locally available embedded CJK font. It accepts the run directory and renders only from standard artifacts.

The PDF uses a stable A4 institutional-report layout:

1. cover: topic, as-of date, profile/pack, and run status;
2. executive summary: stance, confidence, and action bias;
3. key findings from the existing report and structured outputs;
4. data and coverage: row counts, source classes, facets, and time bounds;
5. risks and contradictions: missing evidence, conflicts, duplicates, and source failures;
6. key evidence: titles, publishers, dates, and clickable URLs;
7. methodology and audit information: run ID, artifact contract, loop status, and artifact notes.

Sections without applicable data are omitted or rendered with an explicit unavailable state. The renderer never invents content to fill a template.

Visual treatment is deliberately restrained: clear typography, one dark-blue accent, consistent spacing, tables, page headers, footers, and page numbers. Complex illustrations and chart-generation dependencies are out of scope.

## 5. Job-market Profile Improvements

These rules apply only to `job_market`; they do not alter other research profiles.

### 5.1 Default geography

When a job-market scope does not specify geography, it defaults to `US`. An explicit user geography overrides the default. No additional complex geography inference is added in this iteration.

### 5.2 Active official postings

An official ATS posting that is still discoverable or successfully fetched in the current run remains `active`. An old publication date is recorded as age context but does not by itself make the posting stale or inactive.

A role becomes inactive only when the source explicitly marks it closed or the official posting is no longer available. When the engine cannot determine status, it remains `unknown` rather than being rejected as inactive.

### 5.3 Job identity and deduplication

Job identity uses the first available stable key:

1. ATS requisition or job ID;
2. canonical job URL;
3. normalized company, title, and location tuple.

Description similarity may flag suspected duplicates but must not delete roles with distinct stable identities. This prevents different locations or requisitions sharing a description from collapsing into one row.

## 6. Error Handling

- Rendering exceptions are caught at the PDF boundary and serialized to `pdf_report_status.json` without exposing secrets.
- Partial research runs still receive a PDF that clearly labels their status and limitations.
- Missing optional artifacts cause section omission, not renderer failure.
- Missing mandatory report input produces a failed PDF status and an actionable CLI warning.
- URLs are sanitized before inclusion; local sensitive paths and secret-like values continue to use the existing artifact security rules.
- PDF output is written atomically so interrupted rendering does not leave a file that appears complete.

## 7. Testing

### 7.1 Unit and artifact tests

- A discoverable official job remains active even when its publication date is outside the usual freshness window.
- Similar descriptions with distinct ATS IDs or canonical URLs remain distinct jobs.
- A job-market scope without geography resolves to `US`; an explicit geography is preserved.
- Repair output retains time, role, company/entity, comparison, and required source constraints.
- Date extraction keeps `published_at`, `updated_at`, and `observed_at` distinct.
- A terminal run writes `research_report.pdf`, `pdf_report_status.json`, and manifest references.
- A simulated renderer failure remains non-fatal and is disclosed.
- PDF text extraction contains the topic, status, core headings, Chinese text where supplied, and evidence URLs.

### 7.2 Regression coverage

The suite must cover:

- generic market research;
- technical/GitHub research;
- job-market research;
- dry-run and insufficient-evidence runs;
- warning and source-failure behavior.

The existing full test suite must pass without weakening freshness, source safety, validity, or claim-grounding gates.

### 7.3 Live acceptance

Run the improved engine on the United States SDE/FDE employment-market topic. Inspect the standard run artifacts required by the Research Engine skill, then render the final PDF to PNG with Poppler and review every page for:

- clipped or overlapping text;
- missing glyphs or black squares;
- unreadable tables;
- inconsistent headers, footers, or page numbering;
- broken section transitions;
- missing human-readable citations.

The final delivery includes the engine changes, tests, reusable automatic PDF capability, and the regenerated employment-market report PDF.

## 8. Acceptance Criteria

The work is complete only when:

1. every terminal run attempts PDF generation by default;
2. successful rendering produces the three standard report artifacts;
3. PDF failure cannot change a research run from complete to failed;
4. current official ATS jobs are not rejected solely because of age;
5. stable job identities take precedence over description similarity;
6. job-market scopes default to the United States when geography is omitted;
7. repair retains mandatory query constraints;
8. time extraction distinguishes publication, update, and observation dates;
9. the complete automated test suite passes;
10. the live SDE/FDE run is inspected and its final PDF passes page-by-page visual QA.

## 9. Implementation Boundary

Use the smallest existing extension points:

- add one focused PDF rendering module;
- call it once at the end of the existing artifact-writing path;
- adjust the shared repair and temporal helpers rather than patching callers;
- adjust job status and identity only inside the job-market path;
- reuse existing ReportLab code and bundled dependencies;
- avoid new frameworks, services, and speculative abstractions.
