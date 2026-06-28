"""Shared data models for Research Engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class CollectionRequest:
    source: dict[str, Any]
    topic: str
    run_date: str
    depth: str
    max_results: int

    @property
    def source_id(self) -> str:
        return str(self.source.get("source_id") or "")


@dataclass(frozen=True)
class CollectionResult:
    source_id: str
    connector: str
    rows: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResearchRunResult:
    run_id: str
    run_dir: str
    topic: str
    pack_id: str
    status: str
    dry_run: bool
    raw_rows: int
    loop_status: str = ""
    stop_reason: str = ""
    feedback_action_count: int = 0
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["run_status"] = self.status
        return payload
