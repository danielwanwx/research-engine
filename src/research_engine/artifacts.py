"""Artifact writing utilities."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Any


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug[:64] or "research-run"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    path.write_text((text + "\n") if text else "", encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    """Append one JSON object with one O_APPEND write."""

    path.parent.mkdir(parents=True, exist_ok=True)
    line = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        if os.write(descriptor, line) != len(line):
            raise OSError(f"short append to {path}")
    finally:
        os.close(descriptor)


def render_report(
    *,
    topic: str,
    pack_id: str,
    raw_rows: list[dict[str, Any]],
    claim_review: dict[str, Any],
    decision_brief: dict[str, Any],
    quality_report: dict[str, Any] | None = None,
    loop_record: dict[str, Any] | None = None,
    status: str = "unknown",
    profile: str = "generic",
    as_of: str = "",
    facet_coverage: dict[str, Any] | None = None,
    job_market_snapshot: dict[str, Any] | None = None,
) -> str:
    overall = claim_review.get("overall") or {}
    quality = quality_report or {}
    lines = [
        f"# Research Report: {topic}",
        "",
        f"- Pack: `{pack_id}`",
        f"- Profile: `{profile}`",
        f"- As of: `{as_of or 'unknown'}`",
        f"- Run status: `{status}`",
        f"- Raw rows: `{len(raw_rows)}`",
        f"- Stance: `{overall.get('stance') or 'unknown'}`",
        f"- Confidence: `{overall.get('confidence') or 'unknown'}`",
        f"- Action bias: `{decision_brief.get('action_bias') or 'unknown'}`",
        f"- Average evidence quality: `{quality.get('average_quality_score', 0.0)}`",
        f"- Duplicate clusters: `{quality.get('duplicate_cluster_count', 0)}`",
        f"- Conflict flags: `{len(quality.get('conflict_flags') or [])}`",
        "",
        "## Executive Summary",
        "",
        str(decision_brief.get("headline") or overall.get("summary") or "No summary available."),
    ]
    for rationale in decision_brief.get("rationale") or []:
        lines.append(f"- {rationale}")

    coverage = facet_coverage or quality.get("facet_coverage") or {}
    if coverage:
        lines.extend(
            [
                "",
                "## Scope and Coverage",
                "",
                f"- Required facets: `{coverage.get('required_facets', 0)}`",
                f"- Required facets covered: `{coverage.get('required_facets_covered', 0)}`",
                "- Missing required facets: "
                + (", ".join(coverage.get("missing_required_facets") or []) or "none"),
            ]
        )

    snapshot = job_market_snapshot or {}
    if snapshot:
        counts = snapshot.get("counts") or {}
        snapshot_coverage = snapshot.get("coverage") or {}
        lines.extend(
            [
                "",
                "## Job Market Snapshot",
                "",
                "| Metric | Count |",
                "|---|---:|",
                f"| Observed rows | {counts.get('observed', 0)} |",
                f"| Active openings | {counts.get('active', 0)} |",
                f"| Closed | {counts.get('closed', 0)} |",
                f"| Duplicates | {counts.get('duplicate', 0)} |",
                f"| Rejected | {counts.get('rejected', 0)} |",
                f"| Unknown status | {counts.get('unknown_status', 0)} |",
                "",
                f"- Companies checked: `{snapshot_coverage.get('checked_count', 0)}` / "
                f"`{snapshot_coverage.get('denominator', 0)}`",
                f"- Trend status: `{snapshot.get('trend_status') or 'unknown'}`",
            ]
        )

    lines.extend(
        [
            "",
        "## Evidence",
        ]
    )
    rows_by_id = {str(row.get("evidence_id") or ""): row for row in raw_rows}
    preview_ids = [str(value) for value in quality.get("relevance_preview_evidence_ids") or []]
    preview_rows = [rows_by_id[value] for value in preview_ids if value in rows_by_id]
    for row in (preview_rows or raw_rows)[:20]:
        title = str(row.get("title") or row.get("url") or "Untitled")
        url = str(row.get("url") or row.get("source_url") or "")
        tier = str(row.get("quality_tier") or "unknown")
        duplicate = " duplicate" if row.get("is_duplicate") else ""
        lines.append(f"- [{title}]({url}) - quality `{tier}`{duplicate}")
    risk_flags = list(
        dict.fromkeys(
            [
                *(quality.get("warnings") or []),
                *((claim_review.get("overall") or {}).get("risk_flags") or []),
            ]
        )
    )
    if risk_flags:
        lines.extend(["", "## Evidence Quality Warnings"])
        for warning in risk_flags[:12]:
            lines.append(f"- {warning}")
    loop = loop_record or {}
    if loop:
        lines.extend(
            [
                "",
                "## Loop Status",
                f"- Loop status: `{loop.get('loop_status') or 'unknown'}`",
                f"- Stop reason: `{loop.get('stop_reason') or 'unknown'}`",
            ]
        )
        feedback_actions = loop.get("feedback_actions") or []
        if feedback_actions:
            lines.append("- Feedback actions:")
            for action in feedback_actions[:5]:
                lines.append(
                    f"  - `{action.get('reason') or 'review'}`: {action.get('action') or ''}"
                )
    return "\n".join(lines) + "\n"
