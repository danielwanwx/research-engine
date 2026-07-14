from __future__ import annotations

import json

from research_engine.connectors.xai_discovery import XaiDiscoveryConnector
from research_engine.execution import ConnectorExecutionOptions, execute_collection_requests
from research_engine.models import CollectionRequest, CollectionResult
from research_engine.runner import ResearchEngine, build_source_requests
from research_engine.targets import ResearchTarget


TARGET = ResearchTarget.from_mapping(
    {
        "company": "Stripe",
        "role_family": "software_engineering",
        "role_title": "Staff Backend Engineer",
        "level": "staff",
        "geography": "US",
    }
)


def _request(**source):
    return CollectionRequest(
        source={
            "source_id": "xai_target_discovery",
            "connector": "xai_discovery",
            "target": TARGET.as_dict(),
            **source,
        },
        topic="Stripe Staff Backend Engineer US",
        run_date="2026-07-14",
        depth="quick",
        max_results=3,
    )


def test_structured_target_does_not_add_paid_discovery_by_default():
    requests = build_source_requests({}, topic="target", target=TARGET)

    assert [row.source["connector"] for row in requests] == ["official_job_discovery"]


def test_paid_discovery_requires_explicit_flag_and_positive_budget():
    no_budget = build_source_requests(
        {},
        topic="target",
        target=TARGET,
        paid_discovery=True,
        paid_call_budget=0,
    )
    approved = build_source_requests(
        {},
        topic="target",
        target=TARGET,
        paid_discovery=True,
        paid_call_budget=1,
    )

    assert all(row.source["connector"] != "xai_discovery" for row in no_budget)
    xai = next(row for row in approved if row.source["connector"] == "xai_discovery")
    assert xai.source["paid_call_approved"] is True
    assert xai.source["paid_call_budget"] == 1


def test_xai_real_transport_is_blocked_under_pytest(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "xai-sentinel")
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "sentinel::xai")
    attempts = 0

    def transport(**kwargs):
        nonlocal attempts
        attempts += 1
        raise AssertionError("xAI opened a live transport under pytest")

    monkeypatch.setattr("research_engine.connectors.xai_discovery.post_xai_response", transport)
    result = XaiDiscoveryConnector().collect(
        _request(paid_call_approved=True, paid_call_budget=1)
    )

    assert result.metadata["status"] == "blocked"
    assert result.metadata["stop_reason"] == "blocked_in_test"
    assert attempts == 0


def test_xai_key_alone_is_not_authorization(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "xai-sentinel")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("RESEARCH_ENGINE_EXTERNAL_CALLS_DISABLED", raising=False)
    attempts = 0

    def transport(**kwargs):
        nonlocal attempts
        attempts += 1
        raise AssertionError("xAI key alone opened the transport")

    monkeypatch.setattr("research_engine.connectors.xai_discovery.post_xai_response", transport)
    result = XaiDiscoveryConnector().collect(_request())

    assert result.metadata["status"] == "blocked"
    assert result.metadata["stop_reason"] == "paid_calls_not_approved"
    assert attempts == 0


def test_xai_explicit_approval_and_positive_budget_allow_one_attempt(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "xai-sentinel")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("RESEARCH_ENGINE_EXTERNAL_CALLS_DISABLED", raising=False)
    attempts = 0

    def transport(**kwargs):
        nonlocal attempts
        attempts += 1
        return {
            "citations": ["https://stripe.com/jobs/listing/staff-backend-engineer/123"],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }

    monkeypatch.setattr("research_engine.connectors.xai_discovery.post_xai_response", transport)
    result = XaiDiscoveryConnector().collect(
        _request(paid_call_approved=True, paid_call_budget=1)
    )

    assert result.metadata["status"] == "ready"
    assert result.metadata["stop_reason"] == "within_budget"
    assert result.metadata["paid_calls_attempted"] == 1
    assert attempts == 1


def test_paid_connector_is_never_retried_by_execution_layer():
    attempts = 0

    class Crash:
        def collect(self, request):
            nonlocal attempts
            attempts += 1
            raise RuntimeError("paid upstream failed")

    _, _, report = execute_collection_requests(
        [_request(paid_call_approved=True, paid_call_budget=1)],
        connector_providers={"xai_discovery": Crash},
        options=ConnectorExecutionOptions(retries=3),
    )

    assert attempts == 1
    assert report["requests"][0]["attempts"] == 1


def test_research_run_always_writes_a_sanitized_cost_record(tmp_path):
    class EmptyOfficial:
        connector_id = "official_job_discovery"

        def collect(self, request):
            return CollectionResult(
                source_id=request.source_id,
                connector=self.connector_id,
                rows=[],
            )

    result = ResearchEngine(
        output_dir=tmp_path,
        connectors={"official_job_discovery": EmptyOfficial()},
    ).run(
        "Stripe Staff Backend Engineer US",
        pack_id="interview_prep",
        target=TARGET,
        run_date="2026-07-14",
    )

    record = json.loads((tmp_path / result.run_id / "cost_record.json").read_text())
    assert record == {
        "paid_calls_allowed": 0,
        "paid_calls_attempted": 0,
        "paid_calls_completed": 0,
        "provider_usage": [],
        "estimated_cost_usd": None,
        "budget_status": "not_enabled",
        "stop_reason": "paid_discovery_disabled",
    }
