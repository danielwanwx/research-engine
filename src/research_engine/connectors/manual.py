"""Manual evidence connector."""

from __future__ import annotations

from research_engine.models import CollectionRequest, CollectionResult, utc_now


class ManualConnector:
    connector_id = "manual"

    def collect(self, request: CollectionRequest) -> CollectionResult:
        rows: list[dict] = []
        for index, row in enumerate(request.source.get("rows") or [], start=1):
            if not isinstance(row, dict):
                continue
            normalized = dict(row)
            normalized.setdefault("source_id", request.source_id)
            normalized.setdefault("connector", self.connector_id)
            normalized.setdefault("title", normalized.get("url") or f"Manual evidence {index}")
            normalized.setdefault("captured_at", utc_now())
            normalized.setdefault("text", normalized.get("text_excerpt") or "")
            rows.append(normalized)
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=rows[: request.max_results],
        )
