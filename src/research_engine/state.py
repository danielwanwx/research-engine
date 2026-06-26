"""Local state helpers for Research Engine."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_STATE_DIR = Path("state")
CONNECTOR_CAPABILITIES_FILE = "connector_capabilities.json"


def resolve_state_path(state_dir: Path | None, filename: str) -> Path:
    return (state_dir or DEFAULT_STATE_DIR) / filename


def write_state_json(state_dir: Path | None, filename: str, payload: dict[str, Any]) -> Path:
    path = resolve_state_path(state_dir, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def read_state_json(state_dir: Path | None, filename: str) -> dict[str, Any]:
    path = resolve_state_path(state_dir, filename)
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}
