# PDF Typography Consistency Design

**Date:** 2026-07-16  
**Status:** Approved for implementation

## Problem

The generated Chinese report is visually inconsistent even when adjacent text
uses nearly the same nominal point size. The committed PDF embeds Heiti TC
subsets plus Helvetica, uses a Traditional Chinese face for Simplified Chinese
content, and gives body, list, and bullet elements slightly different sizes.
Latin glyph proportions in Heiti TC make mixed Chinese-English lines look as if
their font size changes mid-sentence.

## Scope

Fix the shared ReportLab renderer and regenerate the existing US SDE/FDE report.
Do not add a theme system, font configuration surface, or new dependency.

## Typography

Use one pan-CJK sans-serif family for Chinese, Latin, numbers, links, inline
bold text, bullets, headers, and footers.

Font preference order:

1. macOS Hiragino Sans GB W3 (TTC index 0) and W6 (TTC index 2).
2. Linux Noto Sans CJK Regular and Bold.
3. macOS Heiti SC Light and Medium (TTC index 1).
4. ReportLab's CJK CID fallback when no embeddable family is available.

The normal hierarchy is deliberately limited:

| Element | Size | Leading |
|---|---:|---:|
| Title | 22 pt | 28 pt |
| Section heading | 15 pt | 20 pt |
| Subsection heading | 11.5 pt | 16 pt |
| Body, bullets, numbered items | 9.5 pt | 14.5 pt |
| Tables | 8 pt | 11.5 pt |
| Header and footer | 7 pt | n/a |

List markers must explicitly inherit the body font and size so ReportLab does
not silently render them in Helvetica. Inline links and bold spans must preserve
their surrounding size.

## Data Flow

`research_report.md` continues through the existing shared renderer. Font
registration selects the first complete regular/bold pair, styles consume that
pair, and the atomic PDF write remains unchanged. The final job-market PDF is
regenerated from its existing Markdown source with this same renderer so the
example artifact and future automatic reports cannot diverge again.

## Failure Handling

If a preferred font is missing or cannot be registered, the renderer tries the
next complete pair. If all embeddable pairs fail, it uses the existing CJK CID
fallback and records that mode in `pdf_report_status.json`. PDF generation
remains non-fatal to the research run.

## Verification

- Unit-test the Hiragino TTC indices and font preference order.
- Assert body, bullet, and numbered styles use one font and one size.
- Inspect rendered page resources to ensure Helvetica is absent.
- Run the full test suite and Ruff.
- Regenerate the six-page report, render every page to PNG, and visually check
  mixed Chinese-English lines, list markers, headings, tables, clipping, and
  page breaks.

## Acceptance Criteria

- Mixed Chinese-English body text has consistent optical weight and size.
- Body paragraphs and lists no longer exhibit 9.0/9.1/8.8 pt drift.
- No accidental Helvetica font resource appears in the regenerated PDF.
- The final PDF remains selectable, searchable, linked, six pages, and A4.
