"""Artifact writing utilities."""

from __future__ import annotations

import json
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


def render_report(
    *,
    topic: str,
    pack_id: str,
    raw_rows: list[dict[str, Any]],
    claim_review: dict[str, Any],
    decision_brief: dict[str, Any],
    quality_report: dict[str, Any] | None = None,
    loop_record: dict[str, Any] | None = None,
) -> str:
    overall = claim_review.get("overall") or {}
    quality = quality_report or {}
    lines = [
        f"# Research Report: {topic}",
        "",
        f"- Pack: `{pack_id}`",
        f"- Raw rows: `{len(raw_rows)}`",
        f"- Stance: `{overall.get('stance') or 'unknown'}`",
        f"- Confidence: `{overall.get('confidence') or 'unknown'}`",
        f"- Action bias: `{decision_brief.get('action_bias') or 'unknown'}`",
        f"- Average evidence quality: `{quality.get('average_quality_score', 0.0)}`",
        f"- Duplicate clusters: `{quality.get('duplicate_cluster_count', 0)}`",
        f"- Conflict flags: `{len(quality.get('conflict_flags') or [])}`",
        "",
        "## Evidence",
    ]
    for row in raw_rows[:20]:
        title = str(row.get("title") or row.get("url") or "Untitled")
        url = str(row.get("url") or row.get("source_url") or "")
        tier = str(row.get("quality_tier") or "unknown")
        duplicate = " duplicate" if row.get("is_duplicate") else ""
        lines.append(f"- [{title}]({url}) - quality `{tier}`{duplicate}")
    if quality.get("warnings"):
        lines.extend(["", "## Evidence Quality Warnings"])
        for warning in quality.get("warnings") or []:
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
