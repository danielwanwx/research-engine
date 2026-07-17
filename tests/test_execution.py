from research_engine.execution import (
    ConnectorExecutionOptions,
    execute_collection_requests,
    retry_delay_seconds,
    retry_after_seconds,
)
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


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.waits = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.waits.append(seconds)
        self.now += seconds


class RetryAfterError(RuntimeError):
    retry_after_seconds = 2
    code = 429


class RateLimitedConnector:
    calls = 0

    def collect(self, request):
        self.__class__.calls += 1
        raise RetryAfterError("upstream secret response")


class AlwaysFailConnector:
    def collect(self, request):
        raise TimeoutError("temporary")


class MetadataStatusConnector:
    def __init__(self, status):
        self.status = status

    def collect(self, request):
        return CollectionResult(
            source_id=request.source_id,
            connector="web_page",
            rows=[],
            warnings=[self.status],
            metadata={"status": self.status},
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


def test_execution_records_query_facet_and_pass_lineage():
    request = CollectionRequest(
        source={
            "source_id": "search-pricing",
            "connector": "manual",
            "query_id": "q-0004",
            "facet_id": "pricing",
            "pass_id": "pass-1",
        },
        topic="market",
        run_date="2026-07-16",
        depth="quick",
        max_results=3,
    )

    results, _, report = execute_collection_requests(
        [request],
        connector_providers={"manual": CountingConnector},
        options=ConnectorExecutionOptions(backoff_base_seconds=0),
    )

    record = report["requests"][0]
    assert record["query_id"] == "q-0004"
    assert record["facet_id"] == "pricing"
    assert record["pass_id"] == "pass-1"
    assert results[0].rows[0]["query_id"] == "q-0004"
    assert results[0].rows[0]["facet_id"] == "pricing"


def test_retry_schedule_is_exponential_jittered_and_capped():
    assert retry_delay_seconds(1, base=1, cap=5, jitter=0) == 0.5
    assert retry_delay_seconds(2, base=1, cap=5, jitter=1) == 2
    assert retry_delay_seconds(8, base=1, cap=5, jitter=1) == 5


def test_retry_after_reads_safe_numeric_header():
    class HeaderError(RuntimeError):
        headers = {"Retry-After": "7"}

    assert retry_after_seconds(HeaderError()) == 7


def test_retry_waits_with_injected_clock_and_records_schedule():
    FlakyConnector.calls = 0
    waits = []
    request = CollectionRequest(
        source={"source_id": "manual_rows", "connector": "manual", "pass_id": "pass-1"},
        topic="topic",
        run_date="2026-07-16",
        depth="quick",
        max_results=3,
    )

    _, _, report = execute_collection_requests(
        [request],
        connector_providers={"manual": FlakyConnector},
        options=ConnectorExecutionOptions(
            retries=1,
            backoff_base_seconds=1,
            sleep_fn=waits.append,
            jitter_fn=lambda: 0,
        ),
    )

    assert waits == [0.5]
    assert report["requests"][0]["retry_delays_seconds"] == [0.5]


def test_retry_after_never_sleeps_past_overall_deadline():
    RateLimitedConnector.calls = 0
    clock = FakeClock()
    request = CollectionRequest(
        source={"source_id": "limited", "connector": "limited"},
        topic="topic",
        run_date="2026-07-16",
        depth="quick",
        max_results=3,
    )

    _, warnings, report = execute_collection_requests(
        [request],
        connector_providers={"limited": RateLimitedConnector},
        options=ConnectorExecutionOptions(
            retries=5,
            overall_deadline_seconds=3,
            backoff_base_seconds=0,
            backoff_cap_seconds=2,
            monotonic_fn=clock.monotonic,
            sleep_fn=clock.sleep,
        ),
    )

    assert clock.waits == [2]
    assert clock.now == 2
    assert RateLimitedConnector.calls == 2
    assert report["requests"][0]["status"] == "rate_limit"
    assert report["requests"][0]["deadline_exhausted"] is True
    assert "upstream secret response" not in " ".join(warnings)


def test_retry_after_is_bounded_without_an_overall_deadline():
    RateLimitedConnector.calls = 0
    clock = FakeClock()
    request = CollectionRequest(
        source={"source_id": "limited", "connector": "limited"},
        topic="topic",
        run_date="2026-07-16",
        depth="quick",
        max_results=3,
    )

    _, _, report = execute_collection_requests(
        [request],
        connector_providers={"limited": RateLimitedConnector},
        options=ConnectorExecutionOptions(
            retries=1,
            overall_deadline_seconds=None,
            backoff_base_seconds=0,
            backoff_cap_seconds=1,
            monotonic_fn=clock.monotonic,
            sleep_fn=clock.sleep,
        ),
    )

    assert clock.waits == [1]
    assert report["requests"][0]["retry_delays_seconds"] == [1]
    assert report["requests"][0]["status"] == "rate_limit"


def test_non_rate_limit_retry_exhaustion_has_distinct_status():
    request = CollectionRequest(
        source={"source_id": "failing", "connector": "failing"},
        topic="topic",
        run_date="2026-07-16",
        depth="quick",
        max_results=3,
    )

    _, _, report = execute_collection_requests(
        [request],
        connector_providers={"failing": AlwaysFailConnector},
        options=ConnectorExecutionOptions(
            retries=1,
            backoff_base_seconds=0,
            sleep_fn=lambda _seconds: None,
        ),
    )

    assert report["requests"][0]["status"] == "retry_exhausted"


def test_result_connector_statuses_remain_distinct():
    request = CollectionRequest(
        source={"source_id": "web", "connector": "web_page"},
        topic="topic",
        run_date="2026-07-16",
        depth="quick",
        max_results=3,
    )

    for status in ("robots_denied", "rate_limit", "failed"):
        _, _, report = execute_collection_requests(
            [request],
            connector_providers={"web_page": MetadataStatusConnector(status)},
            options=ConnectorExecutionOptions(backoff_base_seconds=0),
        )
        assert report["requests"][0]["status"] == status


def test_failed_connector_results_are_not_cached_as_successful_checks(tmp_path):
    class FailedConnector:
        calls = 0

        def collect(self, request):
            self.__class__.calls += 1
            return CollectionResult(
                source_id=request.source_id,
                connector="official_job_discovery",
                rows=[],
                warnings=["official source unavailable"],
                metadata={"status": "failed", "official_source_retrieved": False},
            )

    request = CollectionRequest(
        source={"source_id": "jobs", "connector": "official_job_discovery"},
        topic="jobs",
        run_date="2026-07-16",
        depth="quick",
        max_results=3,
    )
    options = ConnectorExecutionOptions(cache_dir=tmp_path / "cache")

    _, _, first = execute_collection_requests(
        [request],
        connector_providers={"official_job_discovery": FailedConnector},
        options=options,
    )
    _, _, second = execute_collection_requests(
        [request],
        connector_providers={"official_job_discovery": FailedConnector},
        options=options,
    )

    assert FailedConnector.calls == 2
    assert first["requests"][0]["status"] == "failed"
    assert second["requests"][0]["status"] == "failed"
    assert second["requests"][0]["cache_hit"] is False


def test_per_host_delay_uses_injected_clock_without_real_sleep():
    clock = FakeClock()
    requests = [
        CollectionRequest(
            source={
                "source_id": f"web-{index}",
                "connector": "manual",
                "pages": [{"url": f"https://example.com/page-{index}"}],
            },
            topic="topic",
            run_date="2026-07-16",
            depth="quick",
            max_results=1,
        )
        for index in range(2)
    ]

    _, _, report = execute_collection_requests(
        requests,
        connector_providers={"manual": CountingConnector},
        options=ConnectorExecutionOptions(
            max_workers=1,
            host_delay_seconds=1,
            monotonic_fn=clock.monotonic,
            sleep_fn=clock.sleep,
        ),
    )

    assert clock.waits == [1]
    assert [row["host_wait_seconds"] for row in report["requests"]] == [0.0, 1.0]
    assert all(row["host"] == "example.com" for row in report["requests"])


def test_per_host_concurrency_limit_is_recorded():
    requests = [
        CollectionRequest(
            source={
                "source_id": f"web-{index}",
                "connector": "manual",
                "pages": [{"url": f"https://example.com/page-{index}"}],
            },
            topic="topic",
            run_date="2026-07-16",
            depth="quick",
            max_results=1,
        )
        for index in range(3)
    ]

    _, _, report = execute_collection_requests(
        requests,
        connector_providers={"manual": CountingConnector},
        options=ConnectorExecutionOptions(max_workers=3, host_max_concurrency=1),
    )

    assert report["host_max_concurrency"] == 1
    assert all(row["host"] == "example.com" for row in report["requests"])
