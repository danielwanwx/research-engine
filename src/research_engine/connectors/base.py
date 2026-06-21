"""Connector protocol."""

from __future__ import annotations

from typing import Protocol

from research_engine.models import CollectionRequest, CollectionResult


class Connector(Protocol):
    connector_id: str

    def collect(self, request: CollectionRequest) -> CollectionResult:
        """Collect rows for a source request."""
