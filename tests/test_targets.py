import json
from pathlib import Path

import pytest

from research_engine.connectors.xai_discovery import XaiDiscoveryConnector
from research_engine.company_matrix import load_company_matrix
from research_engine.cli import main
from research_engine.models import CollectionRequest, CollectionResult
from research_engine.packs import select_research_pack
from research_engine.quality import enrich_rows_with_quality
from research_engine.runner import ResearchEngine
from research_engine.synthesis import build_supply_demand_matrix
from research_engine.targets import (
    ResearchTarget,
    build_target_claim_review,
    classify_target_evidence,
    match_geography,
)


TARGET = ResearchTarget.from_mapping(
    {
        "schema_version": "research_target.v1",
        "company": "Stripe",
        "role_family": "software_engineering",
        "role_title": "Staff Backend Engineer",
        "level": "staff",
        "geography": "US",
    }
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_structured_target_requires_complete_versioned_tuple():
    assert TARGET.target_key == "stripe|software_engineering|staff_backend_engineer|staff|us"
    assert TARGET.as_dict()["schema_version"] == "research_target.v1"

    with pytest.raises(ValueError, match="role_title"):
        ResearchTarget.from_mapping(
            {
                "company": "Stripe",
                "role_family": "software_engineering",
                "level": "staff",
                "geography": "US",
            }
        )

    with pytest.raises(ValueError, match="unsupported target schema"):
        ResearchTarget.from_mapping(
            {
                "schema_version": "research_target.v2",
                "company": "Stripe",
                "role_family": "software_engineering",
                "role_title": "Staff Backend Engineer",
                "level": "staff",
                "geography": "US",
            }
        )


def test_stripe_false_positive_rows_are_ineligible_for_target_claims():
    rows = [
        {
            "evidence_id": "ev-0001",
            "connector": "web_page",
            "title": "System Design Primer",
            "url": "https://github.com/donnemartin/system-design-primer",
            "text": "Staff backend interview system design hiring bar.",
            "source_kind": "public_repo",
        },
        {
            "evidence_id": "ev-0002",
            "connector": "web_page",
            "title": "Stripe Careers",
            "url": "https://stripe.com/jobs",
            "text": "Build economic infrastructure. Explore open roles.",
            "source_kind": "career_page",
        },
        {
            "evidence_id": "ev-0003",
            "connector": "web_page",
            "title": "YouTube search",
            "url": "https://www.youtube.com/results?search_query=stripe+staff+backend+interview",
            "text": "Stripe interview loop system design backend staff.",
            "source_kind": "platform_search_page",
        },
        {
            "evidence_id": "ev-0004",
            "connector": "web_page",
            "title": "OpenAI Careers",
            "url": "https://openai.com/careers/",
            "text": "Staff backend engineer responsibilities and interview process.",
            "source_kind": "career_page",
        },
    ]

    classified = classify_target_evidence(rows, target=TARGET, run_date="2026-07-14")
    by_id = {row["evidence_id"]: row for row in classified}

    assert by_id["ev-0001"]["source_class"] == "generic_resource"
    assert by_id["ev-0001"]["claim_fitness"]["disposition"] == "background_only"
    assert "generic_resource" in by_id["ev-0001"]["claim_fitness"]["rejection_reasons"]
    assert by_id["ev-0002"]["claim_fitness"]["disposition"] == "rejected"
    assert "landing_page" in by_id["ev-0002"]["claim_fitness"]["rejection_reasons"]
    assert by_id["ev-0003"]["source_class"] == "discovery_only"
    assert by_id["ev-0003"]["claim_fitness"]["disposition"] == "discovery_only"
    assert "search_page" in by_id["ev-0003"]["claim_fitness"]["rejection_reasons"]
    assert "wrong_company" in by_id["ev-0004"]["claim_fitness"]["rejection_reasons"]
    assert not any(row["claim_fitness"]["eligible_claims"] for row in classified)

    review = build_target_claim_review(TARGET, classified, warnings=[])
    assert review["schema_version"] == "target_claim_review.v1"
    assert review["overall"]["support_level"] == "baseline_only"
    assert review["overall"]["status"] == "unsupported"
    current_role = next(claim for claim in review["claims"] if claim["claim_id"] == "current_official_role")
    interview_loop = next(claim for claim in review["claims"] if claim["claim_id"] == "interview_loop")
    assert current_role["verdict"] == "unsupported"
    assert current_role["eligible_evidence_ids"] == []
    assert interview_loop["verdict"] == "unsupported"


def test_actual_stripe_false_positive_artifact_has_zero_claim_eligible_rows():
    fixture = FIXTURE_DIR / "stripe_false_positive_evidence.jsonl"
    rows = [json.loads(line) for line in fixture.read_text().splitlines() if line.strip()]

    assert len(rows) == 15
    classified = classify_target_evidence(rows, target=TARGET, run_date="2026-07-14")
    assert sum(bool((row["claim_fitness"] or {})["eligible_claims"]) for row in classified) == 0
    assert all(
        row["claim_fitness"]["disposition"] in {
            "background_only",
            "discovery_only",
            "rejected",
        }
        for row in classified
    )
    review = build_target_claim_review(TARGET, classified, warnings=[])
    assert review["overall"]["support_level"] == "baseline_only"
    assert review["overall"]["status"] == "unsupported"


def test_official_job_source_kind_cannot_self_authorize_unverified_host():
    classified = classify_target_evidence(
        [
            {
                "evidence_id": "ev-unverified",
                "company": "Stripe",
                "connector": "official_job_discovery",
                "source_kind": "official_job_posting",
                "title": "Staff Backend Engineer",
                "url": "https://jobs-example.invalid/jobs/staff-backend-engineer/123",
                "final_url": "https://jobs-example.invalid/jobs/staff-backend-engineer/123",
                "text": (
                    "Stripe Staff Backend Engineer United States responsibilities, "
                    "requirements, backend systems, and API design."
                ),
                "current_status": "active",
                "is_final_page": True,
            }
        ],
        target=TARGET,
        run_date="2026-07-14",
    )

    row = classified[0]
    assert row["source_class"] == "official_jd"
    assert row["claim_fitness"]["disposition"] == "rejected"
    assert "unverified_official_host" in row["claim_fitness"]["rejection_reasons"]
    assert row["claim_fitness"]["eligible_claims"] == []


def test_official_job_source_kind_cannot_self_authorize_careers_landing_page():
    row = classify_target_evidence(
        [
            {
                "evidence_id": "ev-landing",
                "company": "Stripe",
                "source_kind": "official_job_posting",
                "title": "Staff Backend Engineer",
                "url": "https://stripe.com/jobs",
                "final_url": "https://stripe.com/jobs",
                "text": (
                    "Stripe Staff Backend Engineer United States responsibilities, requirements, "
                    "backend systems, and API design. Apply for this job."
                ),
                "current_status": "active",
                "is_final_page": True,
            }
        ],
        target=TARGET,
        run_date="2026-07-14",
    )[0]

    assert row["is_final_page"] is False
    assert "landing_page" in row["claim_fitness"]["rejection_reasons"]
    assert row["claim_fitness"]["eligible_claims"] == []


def test_software_engineering_company_matrix_is_versioned_unique_and_bounded():
    matrix = load_company_matrix()
    companies = matrix["companies"]

    assert matrix["schema_version"] == "software_engineering_company_matrix.v1"
    assert 25 <= len(companies) <= 30
    keys = [row["company_key"] for row in companies]
    assert len(keys) == len(set(keys))
    assert {"stripe", "google", "apple", "amazon", "anthropic"} <= set(keys)
    assert all(row["official_domains"] for row in companies)
    assert all(len(row["official_domains"]) == len(set(row["official_domains"])) for row in companies)
    assert all(
        domain == domain.lower() and "://" not in domain and "/" not in domain
        for row in companies
        for domain in row["official_domains"]
    )


def test_us_geography_does_not_match_ordinary_in_or_or_foreign_locations():
    assert match_geography("US", "Staff engineer in India or London") == "mismatch"
    assert (
        match_geography(
            "US",
            "Build reliable systems in collaboration with design or product partners.",
        )
        == "unknown"
    )
    assert match_geography("US", "San Francisco, CA") == "compatible"


def test_current_role_requires_a_final_current_official_jd():
    rows = classify_target_evidence(
        [
            {
                "evidence_id": "ev-0001",
                "connector": "official_job_discovery",
                "title": "Staff Backend Engineer, Payments",
                "url": "https://stripe.com/jobs/listing/staff-backend-engineer-payments/12345",
                "final_url": "https://stripe.com/jobs/listing/staff-backend-engineer-payments/12345",
                "text": (
                    "Stripe is hiring a Staff Backend Engineer in the United States. "
                    "Responsibilities include designing backend payment systems and APIs."
                ),
                "source_kind": "official_job_posting",
                "current_status": "active",
                "is_final_page": True,
                "published_at": "2026-07-01",
            }
        ],
        target=TARGET,
        run_date="2026-07-14",
    )

    row = rows[0]
    assert row["source_class"] == "official_jd"
    assert row["target_match"]["overall"] in {"exact", "compatible"}
    assert row["claim_fitness"]["disposition"] == "accepted"
    assert "current_official_role" in row["claim_fitness"]["eligible_claims"]

    review = build_target_claim_review(TARGET, rows, warnings=[])
    assert review["overall"]["support_level"] == "role_calibrated"
    assert review["overall"]["status"] == "supported"
    current_role = next(claim for claim in review["claims"] if claim["claim_id"] == "current_official_role")
    assert current_role["verdict"] == "supported"
    assert current_role["eligible_evidence_ids"] == ["ev-0001"]


def test_invalid_official_jd_cannot_support_structured_target_claims():
    rows = classify_target_evidence(
        [
            {
                "evidence_id": "ev-invalid-jd",
                "connector": "web_page",
                "title": "Staff Backend Engineer, Payments",
                "url": "https://stripe.com/jobs/listing/staff-backend-engineer-payments/12345",
                "final_url": "https://stripe.com/jobs/listing/staff-backend-engineer-payments/12345",
                "text": (
                    "Stripe is hiring a Staff Backend Engineer in the United States. "
                    "Responsibilities include backend payment systems and APIs. Continue with Google."
                ),
                "source_kind": "official_job_posting",
                "current_status": "active",
                "is_final_page": True,
                "content_valid": False,
                "content_invalid_reasons": ["login_wall"],
            }
        ],
        target=TARGET,
        run_date="2026-07-14",
    )

    assert rows[0]["claim_fitness"]["disposition"] == "rejected"
    assert "content_invalid" in rows[0]["claim_fitness"]["rejection_reasons"]
    review = build_target_claim_review(TARGET, rows, warnings=[])
    current_role = next(
        claim for claim in review["claims"] if claim["claim_id"] == "current_official_role"
    )
    assert current_role["verdict"] == "unsupported"
    assert current_role["eligible_evidence_ids"] == []


def test_structured_target_discovery_rows_cannot_ground_matrix_or_conflicts():
    pack = select_research_pack("Stripe staff backend interview")
    rows = classify_target_evidence(
        [
            {
                "evidence_id": "ev-discovery",
                "connector": "web_page",
                "title": "Stripe Staff Backend search",
                "url": "https://example.com/search?q=stripe+staff+backend",
                "text": (
                    "Required system design and coding interview topics appear beside a query "
                    "about tight supply and an oversupply glut."
                ),
                "source_kind": "official_target_discovery",
            }
        ],
        target=TARGET,
        run_date="2026-07-16",
    )

    enriched, quality = enrich_rows_with_quality(
        rows,
        topic="Stripe staff backend interview",
        pack=pack,
    )
    matrix = build_supply_demand_matrix(
        topic="Stripe staff backend interview",
        pack=pack,
        rows=enriched,
    )

    assert enriched[0]["source_class"] == "discovery_only"
    assert enriched[0]["claim_eligible"] is False
    assert quality["conflict_flags"] == []
    assert all(node["evidence_ids"] == [] for node in matrix["rows"])


class FalsePositiveTargetConnector:
    connector_id = "official_job_discovery"

    def collect(self, request):
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=[
                {
                    "title": "System Design Primer",
                    "url": "https://github.com/donnemartin/system-design-primer",
                    "text": "Stripe staff backend interview process and hiring bar.",
                    "source_kind": "public_repo",
                },
                {
                    "title": "Stripe Careers",
                    "url": "https://stripe.com/jobs",
                    "text": "Explore jobs at Stripe.",
                    "source_kind": "career_page",
                },
            ],
        )


class EmptyOfficialTargetConnector:
    connector_id = "official_job_discovery"

    def collect(self, request):
        return CollectionResult(source_id=request.source_id, connector=self.connector_id, rows=[])


class CitedStripeTargetConnector:
    connector_id = "xai_discovery"

    def collect(self, request):
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=[
                {
                    "title": "xAI cited candidate",
                    "url": "https://stripe.com/jobs/listing/staff-backend-engineer-payments/12345",
                    "text": "",
                    "source_class": "discovery_only",
                    "source_kind": "discovery_candidate",
                    "is_final_page": False,
                    "discovered_via": "xai_web_search",
                }
            ],
        )


class FakeTargetRefetchConnector:
    connector_id = "web_page"

    def collect(self, request):
        page = request.source["pages"][0]
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=[
                {
                    **page,
                    "connector": self.connector_id,
                    "title": "Staff Backend Engineer, Payments",
                    "final_url": page["url"],
                    "text": (
                        "Stripe is hiring a Staff Backend Engineer in the United States. "
                        "Responsibilities and requirements include backend APIs. Apply for this job."
                    ),
                    "is_final_page": True,
                }
            ],
        )


def test_target_runner_emits_safe_contract_for_thin_false_positive_run(tmp_path):
    engine = ResearchEngine(
        output_dir=tmp_path,
        connectors={"official_job_discovery": FalsePositiveTargetConnector},
    )

    result = engine.run(
        "Stripe Staff Backend Engineer US",
        pack_id="interview_prep",
        target=TARGET,
        run_date="2026-07-14",
        slug="stripe-target-regression",
    )

    run_dir = tmp_path / result.run_id
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    review = json.loads((run_dir / "claim_review.json").read_text())
    loop_record = json.loads((run_dir / "loop_record.json").read_text())

    assert manifest["artifact_contract"] == "target_intelligence.v1"
    assert manifest["target"]["target_key"] == TARGET.target_key
    assert manifest["target_outcome"]["support_level"] == "baseline_only"
    assert manifest["target_outcome"]["status"] == "unsupported"
    assert review["overall"]["support_level"] == "baseline_only"
    assert loop_record["loop_status"] == "complete_with_review_required"
    assert loop_record["stop_reason"] == "target_evidence_threshold_not_met"


def test_target_runner_refetches_xai_citation_before_claim_acceptance(tmp_path):
    engine = ResearchEngine(
        output_dir=tmp_path,
        connectors={
            "official_job_discovery": EmptyOfficialTargetConnector,
            "xai_discovery": CitedStripeTargetConnector,
            "web_page": FakeTargetRefetchConnector,
        },
    )

    result = engine.run(
        "Stripe Staff Backend Engineer US",
        pack_id="interview_prep",
        target=TARGET,
        run_date="2026-07-14",
        slug="stripe-xai-refetch",
    )
    run_dir = tmp_path / result.run_id
    rows = [json.loads(line) for line in (run_dir / "evidence.jsonl").read_text().splitlines()]
    review = json.loads((run_dir / "claim_review.json").read_text())
    execution = json.loads((run_dir / "collection_execution.json").read_text())

    discovery = next(row for row in rows if row["connector"] == "xai_discovery")
    verified = next(row for row in rows if row["source_id"] == "target_discovery_refetch")
    assert discovery["claim_fitness"]["disposition"] == "discovery_only"
    assert verified["claim_fitness"]["disposition"] == "accepted"
    assert verified["source_class"] == "official_jd"
    assert review["overall"]["support_level"] == "role_calibrated"
    assert review["overall"]["status"] == "supported"
    assert execution["request_count"] == 3
    assert {row["source_id"] for row in execution["requests"]} == {
        "official_job_discovery",
        "xai_target_discovery",
        "target_discovery_refetch",
    }


def test_target_runs_are_cache_stable_and_do_not_inflate_duplicates(tmp_path):
    engine = ResearchEngine(
        output_dir=tmp_path / "runs",
        cache_dir=tmp_path / "cache",
        connectors={
            "official_job_discovery": EmptyOfficialTargetConnector(),
            "xai_discovery": CitedStripeTargetConnector(),
            "web_page": FakeTargetRefetchConnector(),
        },
    )

    first = engine.run(
        "Stripe Staff Backend Engineer US",
        pack_id="interview_prep",
        target=TARGET,
        run_date="2026-07-14",
        slug="target-cache-first",
    )
    second = engine.run(
        "Stripe Staff Backend Engineer US",
        pack_id="interview_prep",
        target=TARGET,
        run_date="2026-07-14",
        slug="target-cache-second",
    )

    def artifacts(result):
        run_dir = tmp_path / "runs" / result.run_id
        rows = [json.loads(line) for line in (run_dir / "evidence.jsonl").read_text().splitlines()]
        return (
            rows,
            json.loads((run_dir / "claim_review.json").read_text()),
            json.loads((run_dir / "collection_execution.json").read_text()),
        )

    first_rows, first_review, _ = artifacts(first)
    second_rows, second_review, second_execution = artifacts(second)
    assert len(first_rows) == len(second_rows) == 2
    assert [row["canonical_url"] for row in first_rows] == [
        row["canonical_url"] for row in second_rows
    ]
    assert first_review["target"]["target_key"] == second_review["target"]["target_key"]
    assert first_review["overall"]["support_level"] == second_review["overall"]["support_level"]
    assert first_review["claims"] == second_review["claims"]
    assert second_execution["status_counts"] == {"cache_hit": 3}
    assert all(request["cache_hit"] for request in second_execution["requests"])


def test_xai_discovery_rows_are_citations_only_until_refetched():
    response = {
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "A model-written summary that must never become evidence.",
                    }
                ],
            }
        ],
        "citations": [
            "https://stripe.com/jobs/listing/staff-backend-engineer-payments/12345",
            "https://x.com/example/status/123",
        ],
    }
    connector = XaiDiscoveryConnector(transport=lambda **_: response)
    result = connector.collect(
        CollectionRequest(
            source={
                "source_id": "xai_target_discovery",
                "connector": "xai_discovery",
                "target": TARGET.as_dict(),
            },
            topic="Stripe Staff Backend Engineer US",
            run_date="2026-07-14",
            depth="quick",
            max_results=5,
        )
    )

    assert [row["url"] for row in result.rows] == response["citations"]
    assert all(row["source_class"] == "discovery_only" for row in result.rows)
    assert all(row["is_final_page"] is False for row in result.rows)
    assert all(row["text"] == "" for row in result.rows)
    assert "model-written summary" not in json.dumps(result.rows)


def test_xai_discovery_parses_nested_url_citation_annotations_only():
    response = {
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Ignore model URL https://unverified.example/model-prose",
                        "annotations": [
                            {
                                "type": "url_citation",
                                "url": "https://stripe.com/jobs/listing/staff-backend-engineer/123",
                            },
                            {
                                "type": "url_citation",
                                "url_citation": {"url": "https://x.com/example/status/123"},
                            },
                        ],
                    }
                ],
            }
        ]
    }
    connector = XaiDiscoveryConnector(transport=lambda **_: response)
    result = connector.collect(
        CollectionRequest(
            source={
                "source_id": "xai_target_discovery",
                "connector": "xai_discovery",
                "target": TARGET.as_dict(),
            },
            topic="Stripe Staff Backend Engineer US",
            run_date="2026-07-14",
            depth="quick",
            max_results=5,
        )
    )

    assert [row["url"] for row in result.rows] == [
        "https://stripe.com/jobs/listing/staff-backend-engineer/123",
        "https://x.com/example/status/123",
    ]
    assert "unverified.example" not in json.dumps(result.rows)


def test_xai_discovery_sanitizes_transport_failures(monkeypatch):
    secret = "xai-secret-must-not-leak"
    monkeypatch.setenv("XAI_API_KEY", secret)

    def fail_transport(**kwargs):
        raise RuntimeError(f"upstream body included {secret} and private response content")

    result = XaiDiscoveryConnector(transport=fail_transport).collect(
        CollectionRequest(
            source={
                "source_id": "xai_target_discovery",
                "connector": "xai_discovery",
                "target": TARGET.as_dict(),
            },
            topic="Stripe Staff Backend Engineer US",
            run_date="2026-07-14",
            depth="quick",
            max_results=5,
        )
    )

    rendered = json.dumps({"warnings": result.warnings, "metadata": result.metadata})
    assert result.rows == []
    assert result.metadata["status"] == "failed"
    assert "RuntimeError" in rendered
    assert secret not in rendered
    assert "private response content" not in rendered


def test_cli_structured_target_contract_and_validation(tmp_path, capsys):
    exit_code = main(
        [
            "run",
            "Stripe Staff Backend Engineer US",
            "--pack",
            "interview_prep",
            "--target-company",
            "Stripe",
            "--target-role-family",
            "software_engineering",
            "--target-role-title",
            "Staff Backend Engineer",
            "--target-level",
            "staff",
            "--target-geography",
            "US",
            "--dry-run",
            "--output",
            str(tmp_path),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    manifest = json.loads((tmp_path / payload["run_id"] / "run_manifest.json").read_text())

    assert exit_code == 0
    assert manifest["artifact_contract"] == "target_intelligence.v1"
    assert manifest["target"]["target_key"] == TARGET.target_key

    with pytest.raises(SystemExit):
        main(
            [
                "run",
                "incomplete target",
                "--target-company",
                "Stripe",
                "--dry-run",
                "--output",
                str(tmp_path),
            ]
        )
