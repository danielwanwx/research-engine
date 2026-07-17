from research_engine.connectors.job_discovery import (
    OfficialJobDiscoveryConnector,
    ats_endpoints,
    parse_ashby,
    parse_greenhouse,
    parse_lever,
)
from research_engine.execution import execute_collection_requests
from research_engine.models import CollectionRequest
from research_engine.runner import build_job_market_snapshot_from_run
from research_engine.targets import ResearchTarget, classify_target_evidence


def test_greenhouse_adapter_emits_current_official_job_candidate():
    rows = parse_greenhouse(
        {
            "jobs": [
                {
                    "id": 123,
                    "title": "Senior Staff Software Engineer, API",
                    "absolute_url": "https://job-boards.greenhouse.io/anthropic/jobs/123",
                    "location": {"name": "San Francisco, CA"},
                    "updated_at": "2026-07-10T00:00:00Z",
                    "content": "<p>Responsibilities and requirements for Anthropic API systems.</p>",
                }
            ]
        },
        company="Anthropic",
    )

    assert rows == [
        {
            "company": "Anthropic",
            "title": "Senior Staff Software Engineer, API",
            "url": "https://job-boards.greenhouse.io/anthropic/jobs/123",
            "location": "San Francisco, CA",
            "published_at": "2026-07-10T00:00:00Z",
            "text": "Responsibilities and requirements for Anthropic API systems.",
            "source_kind": "official_job_posting",
            "current_status": "active",
            "ats_provider": "greenhouse",
        }
    ]


def test_ashby_adapter_emits_current_official_job_candidate():
    rows = parse_ashby(
        {
            "jobs": [
                {
                    "id": "abc",
                    "title": "Site Reliability Engineer, Infrastructure",
                    "jobUrl": "https://jobs.ashbyhq.com/posthog/abc",
                    "location": "Remote, US",
                    "publishedAt": "2026-07-09",
                    "descriptionHtml": "<p>Build reliable infrastructure and production systems.</p>",
                    "isListed": True,
                }
            ]
        },
        company="PostHog",
    )

    assert rows[0]["ats_provider"] == "ashby"
    assert rows[0]["company"] == "PostHog"
    assert rows[0]["current_status"] == "active"
    assert rows[0]["url"] == "https://jobs.ashbyhq.com/posthog/abc"
    assert rows[0]["text"] == "Build reliable infrastructure and production systems."


def test_lever_adapter_emits_current_official_job_candidate():
    rows = parse_lever(
        [
            {
                "id": "xyz",
                "text": "Software Engineer, Backend",
                "hostedUrl": "https://jobs.lever.co/palantir/xyz",
                "categories": {"location": "New York, NY"},
                "createdAt": 1783728000000,
                "descriptionPlain": "Responsibilities include backend services and APIs.",
            }
        ],
        company="Palantir",
    )

    assert rows[0]["ats_provider"] == "lever"
    assert rows[0]["current_status"] == "active"
    assert rows[0]["source_kind"] == "official_job_posting"
    assert rows[0]["url"] == "https://jobs.lever.co/palantir/xyz"


def test_outside_matrix_company_gets_dynamic_public_ats_probes():
    endpoints = ats_endpoints("PostHog", registered=[])

    assert endpoints == [
        ("greenhouse", "https://boards-api.greenhouse.io/v1/boards/posthog/jobs?content=true"),
        ("ashby", "https://api.ashbyhq.com/posting-api/job-board/posthog"),
        ("lever", "https://api.lever.co/v0/postings/posthog?mode=json"),
    ]


def test_official_connector_refetches_greenhouse_final_url_before_eligibility():
    target = ResearchTarget.from_mapping(
        {
            "company": "Anthropic",
            "role_family": "software_engineering",
            "role_title": "Senior Staff Software Engineer API",
            "level": "senior staff",
            "geography": "US",
        }
    )

    def json_fetcher(url):
        if "boards/anthropic/jobs" not in url:
            raise LookupError(url)
        return {
            "jobs": [
                {
                    "id": 123,
                    "title": "Senior Staff Software Engineer, API",
                    "absolute_url": "https://job-boards.greenhouse.io/anthropic/jobs/123",
                    "location": {"name": "San Francisco, CA"},
                    "updated_at": "2026-07-10T00:00:00Z",
                    "content": "<p>Responsibilities and requirements for Anthropic API systems.</p>",
                }
            ]
        }

    connector = OfficialJobDiscoveryConnector(
        json_fetcher=json_fetcher,
        text_fetcher=lambda url: (
            "Anthropic Senior Staff Software Engineer API in San Francisco, CA. "
            "Responsibilities and requirements for backend APIs. Apply for this job."
        ),
    )
    result = connector.collect(
        CollectionRequest(
            source={
                "source_id": "official_job_discovery",
                "connector": "official_job_discovery",
                "target": target.as_dict(),
            },
            topic="Anthropic Senior Staff Software Engineer API US",
            run_date="2026-07-14",
            depth="quick",
            max_results=3,
        )
    )

    assert len(result.rows) == 1
    assert result.rows[0]["is_final_page"] is True
    assert result.rows[0]["final_url"] == result.rows[0]["url"]
    classified = classify_target_evidence(result.rows, target=target, run_date="2026-07-14")
    assert classified[0]["claim_fitness"]["disposition"] == "accepted"
    assert classified[0]["claim_fitness"]["eligible_claims"] == ["current_official_role"]


def test_official_connector_bounds_final_page_verification_before_fetching():
    fetches = []
    connector = OfficialJobDiscoveryConnector(
        json_fetcher=lambda url: {
            "jobs": [
                {
                    "title": f"Senior AI Engineer {index}",
                    "absolute_url": f"https://job-boards.greenhouse.io/anthropic/jobs/{index}",
                    "location": {"name": "United States"},
                    "updated_at": "2026-07-10",
                    "content": "Senior AI Engineer responsibilities",
                }
                for index in range(10)
            ]
        }
        if "boards/anthropic/jobs" in url
        else (_ for _ in ()).throw(LookupError(url)),
        text_fetcher=lambda url: fetches.append(url)
        or "Senior AI Engineer in the United States with current responsibilities.",
    )
    target = {
        "company": "Anthropic",
        "role_family": "machine_learning",
        "role_title": "AI Engineer",
        "level": "senior",
        "geography": "US",
    }

    result = connector.collect(
        CollectionRequest(
            source={"source_id": "jobs", "connector": "official_job_discovery", "target": target},
            topic="AI engineer jobs",
            run_date="2026-07-16",
            depth="quick",
            max_results=2,
        )
    )

    assert len(result.rows) == 2
    assert len(fetches) == 2


def test_total_ats_transport_failure_is_explicit_and_not_a_zero_openings_check():
    connector = OfficialJobDiscoveryConnector(
        json_fetcher=lambda url: (_ for _ in ()).throw(OSError("offline")),
    )
    target = {
        "company": "NoSuchCo",
        "role_family": "machine_learning",
        "role_title": "AI Engineer",
        "level": "senior",
        "geography": "US",
    }

    result = connector.collect(
        CollectionRequest(
            source={
                "source_id": "jobs",
                "connector": "official_job_discovery",
                "target": target,
            },
            topic="AI engineer jobs",
            run_date="2026-07-16",
            depth="quick",
            max_results=2,
        )
    )

    assert result.rows == []
    assert result.metadata["status"] == "failed"
    assert result.metadata["official_source_retrieved"] is False
    assert result.metadata["endpoint_attempts"] == 3
    assert result.metadata["endpoint_successes"] == 0
    assert result.metadata["endpoint_failures"] == 3
    assert len(result.warnings) == 3

    _, _, execution = execute_collection_requests(
        [
            CollectionRequest(
                source={
                    "source_id": "jobs",
                    "connector": "official_job_discovery",
                    "target": target,
                    "target_company": "NoSuchCo",
                },
                topic="AI engineer jobs",
                run_date="2026-07-16",
                depth="quick",
                max_results=2,
            )
        ],
        connector_providers={"official_job_discovery": connector},
    )
    snapshot = build_job_market_snapshot_from_run(
        [],
        scope={
            "schema_version": "research_scope.v1",
            "profile": "job_market",
            "as_of": "2026-07-16",
            "filters": {
                "companies": ["NoSuchCo"],
                "geography": ["US"],
                "role_terms": ["AI Engineer"],
                "levels": ["senior"],
            },
        },
        execution_report=execution,
    )

    assert execution["requests"][0]["status"] == "failed"
    assert snapshot["coverage"]["checked"] == []
    assert snapshot["coverage"]["failed"] == ["NoSuchCo"]
