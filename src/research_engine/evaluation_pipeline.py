"""Normalization and artifact-safe evidence evaluation helpers.

The public runner still owns orchestration.  This module owns the boundary
between connector results and the rows that quality, synthesis, and artifacts
consume, which keeps the runner from also being a row-shaping utility module.
"""

from __future__ import annotations

from typing import Any

from research_engine.extraction import build_chunks
from research_engine.freshness import enrich_row_freshness
from research_engine.models import CollectionResult
from research_engine.security import (
    sanitize_for_artifact,
    sensitive_paths,
    sensitive_value_paths,
)


def normalize_rows(results: list[CollectionResult]) -> list[dict[str, Any]]:
    """Normalize connector rows and assign stable run-local evidence IDs."""

    rows: list[dict[str, Any]] = []
    for result in results:
        for row in result.rows:
            normalized = dict(row)
            normalized.setdefault("source_id", result.source_id)
            normalized.setdefault("connector", result.connector)
            normalized.setdefault("url", normalized.get("source_url") or "")
            source_evidence_id = str(normalized.get("evidence_id") or "")
            if source_evidence_id and not normalized.get("source_evidence_id"):
                normalized["source_evidence_id"] = source_evidence_id
            normalized["evidence_id"] = f"ev-{len(rows) + 1:04d}"
            rows.append(normalized)
    return rows


def enrich_rows_with_freshness(
    rows: list[dict[str, Any]],
    *,
    query_plan: dict[str, Any],
    as_of: str,
) -> list[dict[str, Any]]:
    windows: dict[str, int | None] = {}
    for query in query_plan.get("queries") or []:
        facet_id = str(query.get("facet_id") or "")
        window = query.get("freshness_window_days")
        windows[facet_id] = int(window) if window is not None else None
    enriched: list[dict[str, Any]] = []
    for row in rows:
        facet_id = str(row.get("facet_id") or "")
        window = windows.get(facet_id)
        fresh = enrich_row_freshness(row, as_of=as_of, window_days=window)
        fresh["freshness_window_days"] = window
        enriched.append(fresh)
    return enriched


def build_evidence_chunks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expand structured content blocks into citation-ready evidence chunks."""

    chunks: list[dict[str, Any]] = []
    for row in rows:
        blocks = row.get("content_blocks")
        if not isinstance(blocks, list) or not blocks:
            continue
        parent_evidence_id = str(row.get("evidence_id") or "")
        inherited = {
            key: value
            for key, value in row.items()
            if key
            not in {
                "content_blocks",
                "evidence_id",
                "structured_data",
                "tables",
                "text",
                "text_excerpt",
            }
        }
        for chunk in build_chunks(blocks, parent_evidence_id=parent_evidence_id):
            chunk_id = str(chunk["chunk_id"])
            heading = str(chunk.get("heading") or "")
            chunks.append(
                {
                    **inherited,
                    **chunk,
                    "evidence_id": chunk_id,
                    "source_evidence_id": parent_evidence_id,
                    "parent_evidence_id": parent_evidence_id,
                    "is_chunk": True,
                    "record_kind": "evidence_chunk",
                    "title": " — ".join(
                        value
                        for value in (str(row.get("title") or ""), heading)
                        if value
                    ),
                }
            )
    return chunks


def build_analysis_rows(
    rows: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Use semantic chunks in place of truncated parents for analysis and citations."""

    chunked_parent_ids = {str(chunk.get("parent_evidence_id") or "") for chunk in chunks}
    unchunked = [
        row for row in rows if str(row.get("evidence_id") or "") not in chunked_parent_ids
    ]
    return [*unchunked, *chunks]


def sanitize_rows_for_artifacts(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Redact sensitive connector output before it reaches persisted artifacts."""

    sanitized_rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, row in enumerate(rows, start=1):
        sensitive = sorted({*sensitive_paths(row), *sensitive_value_paths(row)})
        safe_row = sanitize_for_artifact(row)
        if not isinstance(safe_row, dict):
            safe_row = {}
        if sensitive:
            row_label = str(
                safe_row.get("evidence_id")
                or safe_row.get("source_id")
                or safe_row.get("title")
                or f"row_{index}"
            )
            warnings.append(
                "artifact sanitation redacted/dropped sensitive field(s) in "
                f"{row_label}: {','.join(sensitive[:8])}"
            )
        sanitized_rows.append(safe_row)
    return sanitized_rows, warnings


def run_status(
    *,
    dry_run: bool,
    rows: list[dict[str, Any]],
    warnings: list[str],
    source_requests: list[Any],
) -> str:
    """Map collection and evidence state to the stable run status contract."""

    if dry_run:
        return "planned"
    if not source_requests:
        return "failed_no_sources"
    if rows:
        return "complete_with_warnings" if warnings else "complete"
    return "failed_no_rows"
