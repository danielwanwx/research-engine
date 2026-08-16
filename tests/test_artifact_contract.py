from __future__ import annotations

from pathlib import Path
import socket
from urllib.error import URLError

from research_engine.connectors.web_search import WebSearchConnector
from research_engine.execution import ConnectorExecutionOptions, execute_collection_requests
from research_engine.models import CollectionRequest


def _anysearch_request() -> CollectionRequest:
    return CollectionRequest(
        source={
            "source_id": "search-q-0001",
            "connector": "web_search",
            "provider": "anysearch",
            "query": "job descriptions",
            "query_id": "q-0001",
            "facet_id": "overview",
        },
        topic="job descriptions",
        run_date="2026-08-15",
        depth="quick",
        max_results=3,
    )


def test_documented_execution_contract_matches_anysearch_network_failure():
    root = Path(__file__).resolve().parents[1]
    documented = "\n".join(
        (root / path).read_text(encoding="utf-8")
        for path in (
            "README.md",
            "docs/artifact-contract.md",
            "skills/research-engine/SKILL.md",
        )
    )
    assert "failed_network" not in documented
    assert "failed_auth" not in documented
    assert "succeeded_no_rows" not in documented
    assert "retry_exhausted" in documented
    assert "failure_reason" in documented
    assert "row_count" in documented

    def unavailable(_request, _timeout):
        raise URLError(socket.gaierror(8, "private DNS detail"))

    _, warnings, report = execute_collection_requests(
        [_anysearch_request()],
        connector_providers={"web_search": WebSearchConnector(transport=unavailable)},
        options=ConnectorExecutionOptions(
            retries=1,
            sleep_fn=lambda _delay: None,
            host_delay_seconds=0,
        ),
    )

    record = report["requests"][0]
    assert record["status"] == "retry_exhausted"
    assert record["failure_reason"] == "dns_resolution_failed"
    assert record["row_count"] == 0
    assert warnings and "TransientNetworkError (dns_resolution_failed)" in warnings[0]
