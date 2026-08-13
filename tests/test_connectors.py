import json
import socket
from urllib.error import URLError

import pytest

from research_engine.connectors.external import ExternalJsonlConnector
from research_engine.connectors.finance import FinanceQuoteConnector
from research_engine.connectors.web import FetchedPage, WebPageConnector
from research_engine.execution import ConnectorExecutionOptions, execute_collection_requests
from research_engine.models import CollectionRequest
from research_engine.network_errors import TransientNetworkError


def test_web_connector_surfaces_timeout_for_execution_retry(monkeypatch):
    def timeout_fetch(url, **_kwargs):
        raise TimeoutError("simulated timeout")

    monkeypatch.setattr("research_engine.connectors.web.fetch_page_result", timeout_fetch)
    with pytest.raises(TransientNetworkError, match="network_timeout"):
        WebPageConnector().collect(
            CollectionRequest(
                source={
                    "source_id": "web_seed_pages",
                    "pages": [{"url": "https://example.com/slow", "title": "Slow page"}],
                },
                topic="slow page research",
                run_date="2026-06-21",
                depth="quick",
                max_results=3,
            )
        )


def test_web_connector_surfaces_robots_denied_status():
    denied = FetchedPage(
        text="",
        final_url="https://example.com/private",
        http_status=None,
        content_type="",
        content_valid=False,
        content_invalid_reasons=("robots_denied",),
        network_status="robots_denied",
        network_telemetry={"robots_status": "denied", "robots_cache_hit": False},
    )
    result = WebPageConnector(fetcher=lambda _url: denied).collect(
        CollectionRequest(
            source={
                "source_id": "web_seed_pages",
                "pages": [{"url": "https://example.com/private", "title": "Private"}],
            },
            topic="robots policy",
            run_date="2026-07-16",
            depth="quick",
            max_results=1,
        )
    )

    assert result.metadata["status"] == "robots_denied"
    assert result.rows[0]["network_status"] == "robots_denied"
    assert result.rows[0]["network_telemetry"]["robots_status"] == "denied"


def test_web_connector_keeps_invalid_row_with_transport_metadata(monkeypatch):
    monkeypatch.setattr(
        "research_engine.connectors.web.fetch_page_result",
        lambda url, **_kwargs: FetchedPage(
            text="",
            final_url=url,
            http_status=200,
            content_type="application/pdf",
            content_valid=False,
            content_invalid_reasons=("unsupported_content_type_application/pdf",),
        ),
    )

    result = WebPageConnector().collect(
        CollectionRequest(
            source={
                "source_id": "web_seed_pages",
                "pages": [{"url": "https://example.com/report.pdf", "title": "PDF"}],
            },
            topic="pdf audit",
            run_date="2026-07-16",
            depth="quick",
            max_results=3,
        )
    )

    assert result.rows[0]["content_valid"] is False
    assert result.rows[0]["content_type"] == "application/pdf"
    assert result.rows[0]["is_final_page"] is False
    assert "unsupported_content_type_application/pdf" in result.warnings[0]


def test_finance_connector_retries_when_all_quotes_hit_transient_network_failure(monkeypatch):
    calls = []

    def timeout_quote(symbol):
        calls.append(symbol)
        raise TimeoutError("simulated quote timeout")

    monkeypatch.setattr("research_engine.connectors.finance.fetch_quote", timeout_quote)
    request = CollectionRequest(
        source={
            "source_id": "finance_quote_watchlist",
            "connector": "finance_quote",
            "tickers": [{"symbol": "MU", "name": "Micron Technology"}],
        },
        topic="quote research",
        run_date="2026-06-21",
        depth="quick",
        max_results=3,
    )
    _, _, report = execute_collection_requests(
        [request],
        connector_providers={"finance_quote": FinanceQuoteConnector()},
        options=ConnectorExecutionOptions(
            retries=1, sleep_fn=lambda _delay: None, host_delay_seconds=0
        ),
    )

    assert calls == ["MU", "MU"]
    assert report["requests"][0]["failure_reason"] == "network_timeout"


def test_web_page_dns_failure_uses_execution_retry(monkeypatch):
    calls = []

    def dns_failure(url, **_kwargs):
        calls.append(url)
        raise URLError(socket.gaierror(8, "private resolver detail"))

    monkeypatch.setattr("research_engine.connectors.web.fetch_page_result", dns_failure)
    request = CollectionRequest(
        source={
            "source_id": "web_seed_pages",
            "connector": "web_page",
            "pages": [{"url": "https://example.com/page", "title": "Page"}],
        },
        topic="page research",
        run_date="2026-08-13",
        depth="quick",
        max_results=1,
    )
    _, _, report = execute_collection_requests(
        [request],
        connector_providers={"web_page": WebPageConnector()},
        options=ConnectorExecutionOptions(
            retries=1, sleep_fn=lambda _delay: None, host_delay_seconds=0
        ),
    )

    assert calls == ["https://example.com/page", "https://example.com/page"]
    assert report["requests"][0]["failure_reason"] == "dns_resolution_failed"


def test_external_jsonl_connector_imports_logged_in_rows(tmp_path):
    evidence_path = tmp_path / "logged_in.jsonl"
    evidence_path.write_text(
        json.dumps(
            {
                "title": "Lenny memory discussion",
                "url": "https://www.lennysnewsletter.com/p/memory",
                "text": "Subscriber-visible notes say HBM supply remains tight.",
                "metadata": {"platform": "lenny"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = ExternalJsonlConnector().collect(
        CollectionRequest(
            source={
                "source_id": "external_evidence_jsonl",
                "paths": [str(evidence_path)],
            },
            topic="memory research",
            run_date="2026-06-21",
            depth="quick",
            max_results=3,
        )
    )

    assert result.warnings == []
    assert result.rows[0]["connector"] == "external_jsonl"
    assert result.rows[0]["platform"] == "lenny"
    assert result.rows[0]["access_mode"] == "external_authorized_capture"


def test_external_jsonl_connector_drops_sensitive_fields(tmp_path):
    evidence_path = tmp_path / "logged_in.jsonl"
    evidence_path.write_text(
        json.dumps(
            {
                "title": "Visible source",
                "url": "https://example.com/source",
                "text": "Visible evidence token=super-secret-token",
                "cookie": "super-secret-cookie",
                "metadata": {
                    "platform": "x",
                    "authorization": "Bearer super-secret-token",
                    "source_confidence": "medium",
                },
                "metrics": {"views": 10, "api_key": "super-secret-key"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = ExternalJsonlConnector().collect(
        CollectionRequest(
            source={
                "source_id": "external_evidence_jsonl",
                "paths": [str(evidence_path)],
            },
            topic="secret hygiene",
            run_date="2026-06-26",
            depth="quick",
            max_results=3,
        )
    )
    serialized = json.dumps(result.rows[0], ensure_ascii=False)

    assert "super-secret-token" not in serialized
    assert "super-secret-cookie" not in serialized
    assert "super-secret-key" not in serialized
    assert "cookie" not in result.rows[0]
    assert result.rows[0]["metrics"]["views"] == 10
    assert result.rows[0]["raw_ref"].startswith("logged_in.jsonl#")
    assert result.rows[0]["raw_ref"].endswith(":1")
    assert result.metadata["paths"][0]["name"] == "logged_in.jsonl"
    assert "path_hash" in result.metadata["paths"][0]
    assert "dropped sensitive field" in result.warnings[0]


def test_external_jsonl_connector_redacts_url_params_and_command_metrics(tmp_path):
    evidence_path = tmp_path / "logged_in.jsonl"
    evidence_path.write_text(
        json.dumps(
            {
                "title": "Visible source",
                "url": "https://example.com/source?access_token=url-secret&sessionid=session-secret&ok=1",
                "text": "Visible evidence",
                "metrics": {
                    "command": ["collector", "--token", "command-secret", "--query", "visible"],
                    "views": 10,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = ExternalJsonlConnector().collect(
        CollectionRequest(
            source={
                "source_id": "external_evidence_jsonl",
                "paths": [str(evidence_path)],
            },
            topic="secret hygiene",
            run_date="2026-06-26",
            depth="quick",
            max_results=3,
        )
    )
    serialized = json.dumps(result.rows[0], ensure_ascii=False)

    assert "url-secret" not in serialized
    assert "session-secret" not in serialized
    assert "command-secret" not in serialized
    assert "ok=1" in serialized
    assert result.rows[0]["metrics"]["command"] == [
        "collector",
        "--token",
        "[REDACTED]",
        "--query",
        "visible",
    ]


def test_external_jsonl_connector_directory_warning_does_not_leak_full_path(tmp_path):
    evidence_path = tmp_path / "evidence_dir.jsonl"
    evidence_path.mkdir()

    result = ExternalJsonlConnector().collect(
        CollectionRequest(
            source={
                "source_id": "external_evidence_jsonl",
                "paths": [str(evidence_path)],
            },
            topic="path hygiene",
            run_date="2026-06-26",
            depth="quick",
            max_results=3,
        )
    )
    warnings = " ".join(result.warnings)

    assert result.rows == []
    assert "could not be read" in warnings
    assert "evidence_dir.jsonl#" in warnings
    assert str(evidence_path.parent) not in warnings


def test_external_jsonl_connector_uses_distinct_hashed_refs_for_same_basename(tmp_path):
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first_path = first_dir / "logged_in.jsonl"
    second_path = second_dir / "logged_in.jsonl"
    payload = {"title": "Visible source", "url": "https://example.com", "text": "Visible evidence"}
    first_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    second_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    result = ExternalJsonlConnector().collect(
        CollectionRequest(
            source={
                "source_id": "external_evidence_jsonl",
                "paths": [str(first_path), str(second_path)],
            },
            topic="path refs",
            run_date="2026-06-26",
            depth="quick",
            max_results=3,
        )
    )

    refs = [row["raw_ref"] for row in result.rows]

    assert refs[0].startswith("logged_in.jsonl#")
    assert refs[1].startswith("logged_in.jsonl#")
    assert refs[0] != refs[1]
    assert str(first_dir) not in json.dumps(result.rows)
    assert str(second_dir) not in json.dumps(result.rows)
