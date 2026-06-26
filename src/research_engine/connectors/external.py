"""External evidence JSONL connector.

This connector is the open-source bridge for logged-in or proprietary collectors:
another process captures permitted visible evidence, exports JSONL, and this
engine imports it without depending on Chrome, cookies, or platform SDKs.
"""

from __future__ import annotations

import json
from pathlib import Path

from research_engine.models import CollectionRequest, CollectionResult, utc_now
from research_engine.security import (
    artifact_path_ref,
    format_artifact_path_ref,
    sanitize_for_artifact,
    sensitive_paths,
)


class ExternalJsonlConnector:
    connector_id = "external_jsonl"

    def collect(self, request: CollectionRequest) -> CollectionResult:
        rows: list[dict] = []
        warnings: list[str] = []
        for path_value in request.source.get("paths") or []:
            path = Path(str(path_value)).expanduser()
            path_ref = format_artifact_path_ref(path)
            if not path.exists():
                warnings.append(f"external_jsonl path not found: {path_ref}")
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeError) as exc:
                warnings.append(
                    f"external_jsonl {path_ref} could not be read: "
                    f"{type(exc).__name__}"
                )
                continue
            for line_number, line in enumerate(lines, start=1):
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    warnings.append(
                        f"external_jsonl {format_artifact_path_ref(path, line_number=line_number)} "
                        f"invalid JSON: {exc}"
                    )
                    continue
                if not isinstance(payload, dict):
                    warnings.append(
                        f"external_jsonl {format_artifact_path_ref(path, line_number=line_number)} "
                        "must be a JSON object"
                    )
                    continue
                sensitive = sensitive_paths(payload)
                if sensitive:
                    warnings.append(
                        f"external_jsonl {format_artifact_path_ref(path, line_number=line_number)} "
                        "dropped sensitive field(s): "
                        + ",".join(sensitive[:8])
                    )
                row = normalize_external_row(payload, request=request, path=path, line_number=line_number)
                rows.append(row)
                if len(rows) >= request.max_results:
                    break
            if len(rows) >= request.max_results:
                break
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=rows,
            warnings=warnings,
            metadata={"paths": [artifact_path_ref(path) for path in request.source.get("paths") or []]},
        )


def normalize_external_row(
    payload: dict,
    *,
    request: CollectionRequest,
    path: Path,
    line_number: int,
) -> dict:
    safe_payload = sanitize_for_artifact(payload)
    if not isinstance(safe_payload, dict):
        safe_payload = {}
    metadata = safe_payload.get("metadata") if isinstance(safe_payload.get("metadata"), dict) else {}
    url = str(safe_payload.get("url") or safe_payload.get("source_url") or "")
    title = str(safe_payload.get("title") or url or f"External evidence {path.name}:{line_number}")
    text = str(safe_payload.get("text") or safe_payload.get("text_excerpt") or "")
    platform = str(safe_payload.get("platform") or metadata.get("platform") or request.source.get("platform") or "external")
    return {
        **safe_payload,
        "source_id": str(safe_payload.get("source_id") or request.source_id),
        "connector": ExternalJsonlConnector.connector_id,
        "title": title,
        "url": url,
        "text": text,
        "platform": platform,
        "captured_at": str(safe_payload.get("captured_at") or metadata.get("captured_at") or utc_now()),
        "source_kind": str(
            safe_payload.get("source_kind")
            or metadata.get("source_kind")
            or request.source.get("source_kind")
            or "external_logged_in_evidence"
        ),
        "source_confidence": str(
            safe_payload.get("source_confidence")
            or metadata.get("source_confidence")
            or request.source.get("source_confidence")
            or "medium_high"
        ),
        "access_mode": str(
            safe_payload.get("access_mode")
            or metadata.get("access_mode")
            or request.source.get("access_mode")
            or "external_authorized_capture"
        ),
        "raw_ref": format_artifact_path_ref(path, line_number=line_number),
    }
