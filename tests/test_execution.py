from research_engine.execution import ConnectorExecutionOptions, execute_collection_requests
from research_engine.models import CollectionRequest, CollectionResult


class FlakyConnector:
    calls = 0

    def collect(self, request):
        self.__class__.calls += 1
        if self.__class__.calls == 1:
            raise TimeoutError("temporary failure")
        return CollectionResult(
            source_id=request.source_id,
            connector="manual",
            rows=[{"title": "Recovered", "text": "retry succeeded"}],
        )


class CountingConnector:
    calls = 0

    def collect(self, request):
        self.__class__.calls += 1
        return CollectionResult(
            source_id=request.source_id,
            connector="manual",
            rows=[{"title": f"Call {self.__class__.calls}", "text": "cacheable row"}],
        )


def test_execution_retries_failed_connector():
    FlakyConnector.calls = 0
    request = CollectionRequest(
        source={"source_id": "manual_rows", "connector": "manual"},
        topic="topic",
        run_date="2026-06-21",
        depth="quick",
        max_results=3,
    )

    results, warnings, report = execute_collection_requests(
        [request],
        connector_providers={"manual": FlakyConnector},
        options=ConnectorExecutionOptions(retries=1),
    )

    assert warnings == []
    assert len(results) == 1
    assert FlakyConnector.calls == 2
    assert report["requests"][0]["attempts"] == 2
    assert report["requests"][0]["status"] == "ok"


def test_execution_uses_cache_when_enabled(tmp_path):
    CountingConnector.calls = 0
    request = CollectionRequest(
        source={"source_id": "manual_rows", "connector": "manual", "rows": [{"title": "x"}]},
        topic="topic",
        run_date="2026-06-21",
        depth="quick",
        max_results=3,
    )
    options = ConnectorExecutionOptions(cache_dir=tmp_path / "cache")

    first_results, _, first_report = execute_collection_requests(
        [request],
        connector_providers={"manual": CountingConnector},
        options=options,
    )
    second_results, _, second_report = execute_collection_requests(
        [request],
        connector_providers={"manual": CountingConnector},
        options=options,
    )

    assert CountingConnector.calls == 1
    assert first_results[0].rows == second_results[0].rows
    assert first_report["requests"][0]["cache_hit"] is False
    assert second_report["requests"][0]["cache_hit"] is True
