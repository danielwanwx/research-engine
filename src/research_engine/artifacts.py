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
) -> str:
    overall = claim_review.get("overall") or {}
    lines = [
        f"# Research Report: {topic}",
        "",
        f"- Pack: `{pack_id}`",
        f"- Raw rows: `{len(raw_rows)}`",
        f"- Stance: `{overall.get('stance') or 'unknown'}`",
        f"- Confidence: `{overall.get('confidence') or 'unknown'}`",
        f"- Action bias: `{decision_brief.get('action_bias') or 'unknown'}`",
        "",
        "## Evidence",
    ]
    for row in raw_rows[:20]:
        title = str(row.get("title") or row.get("url") or "Untitled")
        url = str(row.get("url") or row.get("source_url") or "")
        lines.append(f"- [{title}]({url})")
    return "\n".join(lines) + "\n"
