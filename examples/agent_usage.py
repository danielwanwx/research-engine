"""Consume a Research Engine summary without loading the full evidence set.

Usage:
    python examples/agent_usage.py runs/2026-08-15-job-descriptions/research_summary.json
"""

from __future__ import annotations

import json
from pathlib import Path
import sys


def load_agent_summary(path: Path) -> dict[str, object]:
    """Load the bounded machine-facing contract used by an agent."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != "research_summary.v1":
        raise ValueError("expected a research_summary.v1 artifact")
    return payload


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: python examples/agent_usage.py <research_summary.json>", file=sys.stderr)
        return 2
    summary = load_agent_summary(Path(args[0]))
    print(summary.get("headline") or "No conclusion available.")
    confidence = summary.get("confidence") or "unknown"
    status = summary.get("status") or "unknown"
    print(f"confidence={confidence} status={status}")
    warnings = [
        str(value)
        for key in ("quality_warnings", "scope_warnings")
        for value in (
            summary.get(key) if isinstance(summary.get(key), list) else []
        )
        if str(value).strip()
    ]
    if warnings:
        print("warnings:")
        for warning in warnings:
            print(f"- {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
