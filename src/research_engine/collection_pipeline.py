"""A narrow seam around connector execution and report merging.

The runner owns research policy and repair decisions.  This module owns the
mechanical connector execution boundary so all passes share one executor and
one merge rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from research_engine.execution import ConnectorExecutionOptions, execute_collection_requests


@dataclass(frozen=True)
class CollectionPipeline:
    """Execute one or more connector passes with consistent options."""

    connector_providers: dict[str, Any]
    options: ConnectorExecutionOptions

    def execute(self, requests: list[Any]) -> tuple[list[Any], list[str], dict[str, Any]]:
        return execute_collection_requests(
            requests,
            connector_providers=self.connector_providers,
            options=self.options,
        )

    @staticmethod
    def merge_reports(*reports: dict[str, Any]) -> dict[str, Any]:
        """Merge pass reports while preserving every per-request outcome."""

        base = dict(reports[0]) if reports else {}
        requests = [request for report in reports for request in report.get("requests") or []]
        status_counts: dict[str, int] = {}
        for request in requests:
            status = str(request.get("status") or "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        base.update(
            {
                "generated_at": _utc_now(),
                "request_count": len(requests),
                "status_counts": status_counts,
                "requests": requests,
            }
        )
        return base


def _utc_now() -> str:
    from research_engine.models import utc_now

    return utc_now()
