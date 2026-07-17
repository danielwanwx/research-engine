from __future__ import annotations

import json

from research_engine.connectors.anysearch import AnySearchConnector
from research_engine.models import CollectionRequest, CollectionResult
from research_engine.runner import ResearchEngine
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
            "source_id": "anysearch_target_discovery",
            "connector": "anysearch_discovery",
            "target": TARGET.as_dict(),
            "query_intent": "official_role",
            "external_discovery_approved": True,
            **source,
        },
        topic="Stripe Staff Backend Engineer US",
        run_date="2026-07-14",
        depth="quick",
        max_results=3,
    )


def _response():
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": (
                        "[Staff Backend Engineer](https://stripe.com/jobs/listing/staff-backend-engineer/123)\n"
                        "[Engineering careers](https://stripe.com/jobs/search)"
                    ),
                }
            ]
        },
    }


def test_anysearch_rows_are_discovery_only_and_keep_provider_rank():
    result = AnySearchConnector(transport=lambda **_: _response()).collect(_request())

    assert [row["provider_rank"] for row in result.rows] == [1, 2]
    assert all(row["connector"] == "anysearch_discovery" for row in result.rows)
    assert all(row["source_class"] == "discovery_only" for row in result.rows)
    assert all(row["authority"] == "candidate_url_only" for row in result.rows)
    assert all(row["is_final_page"] is False for row in result.rows)
    assert all(row["text"] == "" for row in result.rows)


def test_anysearch_request_never_contains_candidate_private_data():
    captured: dict = {}

    def transport(**kwargs):
        captured.update(kwargs["payload"])
        return _response()

    result = AnySearchConnector(transport=transport).collect(
        _request(
            resume_text="PRIVATE_RESUME_SECRET",
            candidate_name="PRIVATE_CANDIDATE_NAME",
            candidate_stories=["PRIVATE_STORY"],
        )
    )

    rendered = json.dumps(captured, sort_keys=True)
    assert result.metadata["status"] == "ready"
    assert "PRIVATE_" not in rendered
    assert "Stripe" in rendered
    assert "Staff Backend Engineer" in rendered


def test_anysearch_real_transport_is_blocked_under_pytest(monkeypatch):
    monkeypatch.setenv("ANYSEARCH_API_KEY", "anysearch-sentinel")
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "sentinel::anysearch")
    attempts = 0

    def transport(**kwargs):
        nonlocal attempts
        attempts += 1
        raise AssertionError("AnySearch opened a live transport under pytest")

    monkeypatch.setattr("research_engine.connectors.anysearch.post_anysearch_response", transport)
    result = AnySearchConnector().collect(_request())

    assert result.metadata["status"] == "blocked"
    assert result.metadata["stop_reason"] == "blocked_in_test"
    assert attempts == 0


class ExactOfficial:
    connector_id = "official_job_discovery"

    def collect(self, request):
        text = (
            "Stripe Staff Backend Engineer in the United States. Responsibilities and requirements "
            "include backend services, APIs, distributed systems, and production ownership. Apply now. "
        ) * 3
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=[
                {
                    "company": "Stripe",
                    "title": "Staff Backend Engineer",
                    "url": "https://stripe.com/jobs/listing/staff-backend-engineer/123",
                    "final_url": "https://stripe.com/jobs/listing/staff-backend-engineer/123",
                    "location": "United States",
                    "text": text,
                    "source_kind": "official_job_posting",
                    "current_status": "active",
                    "is_final_page": True,
                }
            ],
        )


class EmptyOfficial:
    connector_id = "official_job_discovery"

    def collect(self, request):
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=[],
        )


class CountingAnySearch:
    connector_id = "anysearch_discovery"

    def __init__(self, calls):
        self.calls = calls

    def collect(self, request):
        self.calls.append(request.source_id)
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=[],
        )


def test_official_exact_role_skips_anysearch(tmp_path):
    calls: list[str] = []
    engine = ResearchEngine(
        output_dir=tmp_path,
        connectors={
            "official_job_discovery": ExactOfficial(),
            "anysearch_discovery": CountingAnySearch(calls),
        },
    )

    engine.run(
        "Stripe Staff Backend Engineer US",
        pack_id="interview_prep",
        target=TARGET,
        anysearch_discovery=True,
        run_date="2026-07-14",
    )

    assert calls == []


def test_thin_official_result_runs_one_anysearch_request(tmp_path):
    calls: list[str] = []
    engine = ResearchEngine(
        output_dir=tmp_path,
        connectors={
            "official_job_discovery": EmptyOfficial(),
            "anysearch_discovery": CountingAnySearch(calls),
        },
    )

    engine.run(
        "Stripe Staff Backend Engineer US",
        pack_id="interview_prep",
        target=TARGET,
        anysearch_discovery=True,
        run_date="2026-07-14",
    )

    assert calls == ["anysearch_target_discovery"]
