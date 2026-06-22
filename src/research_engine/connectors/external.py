"""External evidence JSONL connector.

This connector is the open-source bridge for logged-in or proprietary collectors:
another process captures permitted visible evidence, exports JSONL, and this
engine imports it without depending on Chrome, cookies, or platform SDKs.
"""

from __future__ import annotations

import json
from pathlib import Path

from research_engine.models import CollectionRequest, CollectionResult, utc_now


class ExternalJsonlConnector:
    connector_id = "external_jsonl"

    def collect(self, request: CollectionRequest) -> CollectionResult:
        rows: list[dict] = []
        warnings: list[str] = []
        for path_value in request.source.get("paths") or []:
            path = Path(str(path_value)).expanduser()
            if not path.exists():
                warnings.append(f"external_jsonl path not found: {path}")
                continue
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    warnings.append(f"external_jsonl {path}:{line_number} invalid JSON: {exc}")
                    continue
                if not isinstance(payload, dict):
                    warnings.append(f"external_jsonl {path}:{line_number} must be a JSON object")
                    continue
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
            metadata={"paths": [str(path) for path in request.source.get("paths") or []]},
        )


def normalize_external_row(
    payload: dict,
    *,
    request: CollectionRequest,
    path: Path,
    line_number: int,
) -> dict:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    url = str(payload.get("url") or payload.get("source_url") or "")
    title = str(payload.get("title") or url or f"External evidence {path.name}:{line_number}")
    text = str(payload.get("text") or payload.get("text_excerpt") or "")
    platform = str(payload.get("platform") or metadata.get("platform") or request.source.get("platform") or "external")
    return {
        **payload,
        "source_id": str(payload.get("source_id") or request.source_id),
        "connector": ExternalJsonlConnector.connector_id,
        "title": title,
        "url": url,
        "text": text,
        "platform": platform,
        "captured_at": str(payload.get("captured_at") or metadata.get("captured_at") or utc_now()),
        "source_kind": str(
            payload.get("source_kind")
            or metadata.get("source_kind")
            or request.source.get("source_kind")
            or "external_logged_in_evidence"
        ),
        "source_confidence": str(
            payload.get("source_confidence")
            or metadata.get("source_confidence")
            or request.source.get("source_confidence")
            or "medium_high"
        ),
        "access_mode": str(
            payload.get("access_mode")
            or metadata.get("access_mode")
            or request.source.get("access_mode")
            or "external_authorized_capture"
        ),
        "raw_ref": f"{path}:{line_number}",
    }
