import json
import socket
from urllib.error import HTTPError, URLError

from research_engine.connectors.web_search import WebSearchConnector
from research_engine.execution import ConnectorExecutionOptions, execute_collection_requests
from research_engine.models import CollectionRequest


def request(*, provider="anysearch", endpoint="", max_results=2):
    return CollectionRequest(
        source={
            "source_id": "search-q-0001",
            "connector": "web_search",
            "provider": provider,
            "endpoint": endpoint,
            "query": "JSON Canvas specification",
            "query_id": "q-0001",
            "facet_id": "primary_sources",
        },
        topic="JSON Canvas specification",
        run_date="2026-07-16",
        depth="quick",
        max_results=max_results,
    )


def test_anysearch_is_anonymous_and_rows_are_discovery_only():
    captured = {}

    def transport(http_request, timeout):
        captured["request"] = http_request
        captured["timeout"] = timeout
        return {
            "code": 0,
            "data": {
                "results": [
                    {
                        "title": "JSON Canvas",
                        "url": "https://jsoncanvas.org/spec/1.0/",
                        "snippet": "An open file format for infinite canvas data.",
                    }
                ],
                "total": 1,
            },
        }

    result = WebSearchConnector(transport=transport).collect(request())
    sent = captured["request"]
    body = json.loads(sent.data.decode("utf-8"))

    assert sent.full_url == "https://api.anysearch.com/v1/search"
    assert sent.get_header("Authorization") is None
    assert body["query"] == "JSON Canvas specification"
    assert body["limit"] == 2
    assert result.rows[0]["source_class"] == "discovery_only"
    assert result.rows[0]["claim_eligible"] is False
    assert result.rows[0]["query_id"] == "q-0001"
    assert result.rows[0]["facet_id"] == "primary_sources"


def test_searxng_uses_only_the_explicit_endpoint_and_bounds_results():
    seen = []

    def transport(http_request, timeout):
        seen.append(http_request.full_url)
        return {
            "results": [
                {"title": str(index), "url": f"https://example.com/{index}", "content": "result"}
                for index in range(30)
            ]
        }

    result = WebSearchConnector(transport=transport).collect(
        request(provider="searxng", endpoint="https://search.example.org/search", max_results=50)
    )

    assert len(seen) == 1
    assert seen[0].startswith("https://search.example.org/search?")
    assert "format=json" in seen[0]
    assert len(result.rows) == 20


def test_none_provider_makes_no_network_request():
    def transport(http_request, timeout):  # pragma: no cover - failure path only
        raise AssertionError("transport must not be called")

    result = WebSearchConnector(transport=transport).collect(request(provider="none"))

    assert result.rows == []
    assert result.warnings == []
    assert result.metadata["status"] == "disabled"


def test_malformed_and_rate_limit_failures_are_sanitized():
    malformed = WebSearchConnector(transport=lambda _request, _timeout: {"code": 0}).collect(request())
    assert malformed.rows == []
    assert malformed.warnings == ["web_search anysearch returned malformed payload"]

    def limited(http_request, timeout):
        raise HTTPError(http_request.full_url, 429, "secret quota body", {}, None)

    limited_result = WebSearchConnector(transport=limited).collect(request())
    warning = limited_result.warnings[0]
    assert "429" in warning
    assert "secret quota body" not in warning
    assert limited_result.metadata["status"] == "rate_limit"

    quota = WebSearchConnector(
        transport=lambda _request, _timeout: {"code": 402, "message": "token=upstream-secret"}
    ).collect(request())
    assert quota.warnings == ["web_search anysearch API error code 402"]

    provider_limited = WebSearchConnector(
        transport=lambda _request, _timeout: {"code": 429, "message": "secret quota body"}
    ).collect(request())
    assert provider_limited.metadata["status"] == "rate_limit"


def test_web_search_rate_limit_matches_execution_status_contract():
    def limited(http_request, timeout):
        raise HTTPError(http_request.full_url, 429, "secret quota body", {}, None)

    connector = WebSearchConnector(transport=limited)
    _, _, report = execute_collection_requests(
        [request()],
        connector_providers={"web_search": connector},
        options=ConnectorExecutionOptions(retries=0, host_delay_seconds=0),
    )

    assert report["requests"][0]["status"] == "rate_limit"


def test_anysearch_dns_failure_uses_execution_retry_and_safe_classification():
    calls = []

    def unavailable(_request, _timeout):
        calls.append("attempt")
        raise URLError(socket.gaierror(8, "host lookup included private detail"))

    _, warnings, report = execute_collection_requests(
        [request()],
        connector_providers={"web_search": WebSearchConnector(transport=unavailable)},
        options=ConnectorExecutionOptions(
            retries=1,
            sleep_fn=lambda _delay: None,
            host_delay_seconds=0,
        ),
    )

    record = report["requests"][0]
    assert calls == ["attempt", "attempt"]
    assert record["attempts"] == 2
    assert record["status"] == "retry_exhausted"
    assert record["failure_reason"] == "dns_resolution_failed"
    assert warnings == [
        "web_search connector crashed for search-q-0001: "
        "TransientNetworkError (dns_resolution_failed)"
    ]
    assert "private detail" not in str(record)


def test_searxng_requires_an_explicit_endpoint():
    result = WebSearchConnector(transport=lambda _request, _timeout: {}).collect(
        request(provider="searxng")
    )

    assert result.rows == []
    assert result.warnings == ["web_search searxng requires an explicit endpoint"]


def test_anysearch_optional_fields_are_bounded_and_sensitive_params_are_removed():
    captured = {}

    def transport(http_request, timeout):
        captured.update(json.loads(http_request.data.decode("utf-8")))
        return {"code": 0, "data": {"results": []}}

    base = request()
    custom = CollectionRequest(
        source={
            **base.source,
            "language": "e" * 200,
            "params": {"api_key": "secret", "safe": "x" * 1000, "nested": {"ignored": True}},
        },
        topic=base.topic,
        run_date=base.run_date,
        depth=base.depth,
        max_results=base.max_results,
    )
    WebSearchConnector(transport=transport).collect(custom)

    assert len(captured["language"]) == 100
    assert captured["params"] == {"safe": "x" * 500}
