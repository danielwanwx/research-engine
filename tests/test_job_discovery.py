from research_engine.connectors.job_discovery import (
    MAX_ATS_CANDIDATES,
    MAX_JSON_BYTES,
    OfficialJobDiscoveryConnector,
    ats_endpoints,
    fetch_json,
    parse_ashby,
    parse_amazon_jobs,
    parse_greenhouse,
    parse_lever,
)
from research_engine.models import CollectionRequest
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


def test_amazon_official_search_adapter_keeps_location_and_full_description():
    rows = parse_amazon_jobs(
        {
            "jobs": [
                {
                    "title": "Software Development Engineer II",
                    "job_path": "/en/jobs/10466814/software-development-engineer-ii",
                    "normalized_location": "North Reading, Massachusetts, USA",
                    "country_code": "USA",
                    "posted_date": "July 6, 2026",
                    "description": "Key job responsibilities for distributed robotics systems.",
                    "basic_qualifications": "3+ years of software development experience.",
                    "preferred_qualifications": "Distributed systems experience.",
                    "url_next_step": "https://account.amazon.jobs/jobs/10466814/apply",
                }
            ]
        },
        company="Amazon",
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["url"] == (
        "https://www.amazon.jobs/en/jobs/10466814/software-development-engineer-ii"
    )
    assert row["location"] == "North Reading, Massachusetts, USA"
    assert row["ats_provider"] == "amazon_jobs"
    assert "Key job responsibilities" in row["text"]
    assert "account.amazon.jobs/jobs/10466814/apply" in row["text"]


def test_outside_matrix_company_gets_dynamic_public_ats_probes():
    endpoints = ats_endpoints("PostHog", registered=[])

    assert endpoints == [
        ("greenhouse", "https://boards-api.greenhouse.io/v1/boards/posthog/jobs?content=true"),
        ("ashby", "https://api.ashbyhq.com/posting-api/job-board/posthog"),
        ("lever", "https://api.lever.co/v0/postings/posthog?mode=json"),
    ]


def test_registered_ats_uses_only_the_configured_provider():
    endpoints = ats_endpoints(
        "Anthropic",
        registered=[{"provider": "greenhouse", "board_token": "anthropic"}],
        registered_company=True,
    )

    assert endpoints == [
        (
            "greenhouse",
            "https://boards-api.greenhouse.io/v1/boards/anthropic/jobs?content=true",
        )
    ]


def test_registered_custom_company_skips_blind_ats_probes():
    assert ats_endpoints("Stripe", registered=[], registered_company=True) == []


def test_connector_caps_target_ranked_final_page_verification():
    target = ResearchTarget.from_mapping(
        {
            "company": "PostHog",
            "role_family": "software_engineering",
            "role_title": "Site Reliability Engineer Infrastructure",
            "level": "unspecified",
            "geography": "US",
        }
    )
    jobs = [
        {
            "id": str(index),
            "title": f"Site Reliability Engineer Infrastructure {index}",
            "jobUrl": f"https://jobs.ashbyhq.com/posthog/{index}",
            "location": "Remote, US",
            "descriptionPlain": "Responsibilities and requirements for reliable infrastructure. " * 4,
            "isListed": True,
        }
        for index in range(20)
    ]
    calls: list[str] = []

    def json_fetcher(url):
        if "ashbyhq.com" in url:
            return {"jobs": jobs}
        raise LookupError(url)

    def text_fetcher(url):
        calls.append(url)
        return "PostHog Site Reliability Engineer Infrastructure. Apply for this job. " * 3

    result = OfficialJobDiscoveryConnector(
        json_fetcher=json_fetcher,
        text_fetcher=text_fetcher,
    ).collect(
        CollectionRequest(
            source={
                "source_id": "official_job_discovery",
                "connector": "official_job_discovery",
                "target": target.as_dict(),
            },
            topic="PostHog SRE Infrastructure US",
            run_date="2026-07-14",
            depth="quick",
            max_results=20,
        )
    )

    assert len(calls) <= MAX_ATS_CANDIDATES
    assert len(result.rows) <= MAX_ATS_CANDIDATES


def test_target_ranking_does_not_verify_unrelated_customer_success_roles():
    target = ResearchTarget.from_mapping(
        {
            "company": "PostHog",
            "role_family": "software_engineering",
            "role_title": "Site Reliability Engineer Infrastructure",
            "level": "unspecified",
            "geography": "US",
        }
    )
    jobs = [
        {
            "title": "Customer Success Manager",
            "jobUrl": "https://jobs.ashbyhq.com/posthog/customer-success",
            "location": "Remote, US",
            "descriptionPlain": "Support customers and manage accounts.",
            "isListed": True,
        },
        {
            "title": "Site Reliability Engineer, Infrastructure",
            "jobUrl": "https://jobs.ashbyhq.com/posthog/sre",
            "location": "Remote, US",
            "descriptionPlain": "Responsibilities and requirements for reliable infrastructure. " * 4,
            "isListed": True,
        },
    ]
    calls: list[str] = []

    def json_fetcher(url):
        if "ashbyhq.com" in url:
            return {"jobs": jobs}
        raise LookupError(url)

    def text_fetcher(url):
        calls.append(url)
        return "Loading... Powered by Ashby"

    result = OfficialJobDiscoveryConnector(
        json_fetcher=json_fetcher,
        text_fetcher=text_fetcher,
    ).collect(
        CollectionRequest(
            source={"source_id": "official_job_discovery", "target": target.as_dict()},
            topic="PostHog SRE",
            run_date="2026-07-14",
            depth="quick",
            max_results=10,
        )
    )

    assert calls == ["https://jobs.ashbyhq.com/posthog/sre"]
    assert [row["title"] for row in result.rows] == [
        "Site Reliability Engineer, Infrastructure"
    ]


def test_fetch_json_rejects_unbounded_board_payload(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, size=-1):
            assert size == MAX_JSON_BYTES + 1
            return b"x" * size

    monkeypatch.setattr(
        "research_engine.connectors.job_discovery.urlopen",
        lambda _request, timeout: Response(),
    )

    try:
        fetch_json("https://api.ashbyhq.com/posting-api/job-board/posthog")
    except ValueError as exc:
        assert "byte limit" in str(exc)
    else:
        raise AssertionError("oversized ATS payload must be rejected")


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


def test_amazon_configured_official_api_supports_exact_role_without_xai_or_search_html():
    target = ResearchTarget.from_mapping(
        {
            "company": "Amazon",
            "role_family": "software_engineering",
            "role_title": "Software Development Engineer II",
            "level": "SDE II",
            "geography": "US",
        }
    )
    requested_urls: list[str] = []

    def json_fetcher(url):
        requested_urls.append(url)
        assert "/en/search.json?" in url
        return {
            "jobs": [
                {
                    "title": "Software Development Engineer II",
                    "job_path": "/en/jobs/10466814/software-development-engineer-ii",
                    "normalized_location": "North Reading, Massachusetts, USA",
                    "country_code": "USA",
                    "posted_date": "July 6, 2026",
                    "description": "Key job responsibilities for distributed robotics systems.",
                    "basic_qualifications": "3+ years of software development experience.",
                    "preferred_qualifications": "Distributed systems experience.",
                    "url_next_step": "https://account.amazon.jobs/jobs/10466814/apply",
                }
            ]
        }

    connector = OfficialJobDiscoveryConnector(
        json_fetcher=json_fetcher,
        html_fetcher=lambda _url: (_ for _ in ()).throw(
            AssertionError("configured Amazon API must not require search shell HTML")
        ),
        text_fetcher=lambda url: (
            "Amazon Software Development Engineer II. North Reading, Massachusetts, USA. "
            "Key job responsibilities and qualifications for distributed systems. Apply now.",
            url,
            "usable",
        ),
    )
    result = connector.collect(
        CollectionRequest(
            source={"source_id": "official_job_discovery", "target": target.as_dict()},
            topic="Amazon SDE II US",
            run_date="2026-07-14",
            depth="audit",
            max_results=5,
        )
    )

    assert len(requested_urls) == 1
    assert len(result.rows) >= 1
    final_rows = [row for row in result.rows if row.get("is_final_page")]
    assert len(final_rows) == 1
    classified = classify_target_evidence(final_rows, target=target, run_date="2026-07-14")
    assert classified[0]["claim_fitness"]["eligible_claims"] == ["current_official_role"]


def test_configured_ats_api_record_is_canonical_when_human_page_is_blocked():
    target = ResearchTarget.from_mapping(
        {
            "company": "Anthropic",
            "role_family": "software_engineering",
            "role_title": "Senior Staff Software Engineer API",
            "level": "senior staff",
            "geography": "US",
        }
    )
    api_text = (
        "Anthropic Senior Staff Software Engineer API in San Francisco, CA. "
        "Responsibilities and requirements for backend API systems. Apply for this job. "
    ) * 3

    connector = OfficialJobDiscoveryConnector(
        json_fetcher=lambda _url: {
            "jobs": [
                {
                    "id": 123,
                    "title": "Senior Staff Software Engineer, API",
                    "absolute_url": "https://job-boards.greenhouse.io/anthropic/jobs/123",
                    "location": {"name": "San Francisco, CA"},
                    "updated_at": "2026-07-10T00:00:00Z",
                    "content": api_text,
                }
            ]
        },
        text_fetcher=lambda _url: "403 ERROR The request could not be satisfied. Request blocked.",
    )
    result = connector.collect(
        CollectionRequest(
            source={"source_id": "official_job_discovery", "target": target.as_dict()},
            topic="Anthropic role",
            run_date="2026-07-14",
            depth="quick",
            max_results=5,
        )
    )

    assert len(result.rows) == 1
    row = result.rows[0]
    assert row["text"] == api_text.strip()
    assert row["is_final_page"] is True
    assert row["ats_ownership_verified"] is True
    assert row["canonical_record_kind"] == "official_ats_api_record"
    classified = classify_target_evidence(result.rows, target=target, run_date="2026-07-14")
    assert classified[0]["claim_fitness"]["eligible_claims"] == ["current_official_role"]


def test_active_api_record_does_not_override_explicitly_closed_human_page():
    target = ResearchTarget.from_mapping(
        {
            "company": "Anthropic",
            "role_family": "software_engineering",
            "role_title": "Senior Staff Software Engineer API",
            "level": "senior staff",
            "geography": "US",
        }
    )
    result = OfficialJobDiscoveryConnector(
        json_fetcher=lambda _url: {
            "jobs": [
                {
                    "title": "Senior Staff Software Engineer, API",
                    "absolute_url": "https://job-boards.greenhouse.io/anthropic/jobs/closed",
                    "location": {"name": "San Francisco, CA"},
                    "content": (
                        "Anthropic Senior Staff Software Engineer API in San Francisco, CA. "
                        "Responsibilities and requirements. Apply for this job. "
                    )
                    * 3,
                }
            ]
        },
        text_fetcher=lambda url: (
            "This job is no longer available.",
            url,
            "not_found_or_closed",
        ),
    ).collect(
        CollectionRequest(
            source={"source_id": "official_job_discovery", "target": target.as_dict()},
            topic="Anthropic role",
            run_date="2026-07-14",
            depth="quick",
            max_results=5,
        )
    )

    assert result.rows == []


def test_unverified_dynamic_ats_slug_cannot_use_api_only_canonical_fallback():
    target = ResearchTarget.from_mapping(
        {
            "company": "Acme Labs",
            "role_family": "software_engineering",
            "role_title": "Backend Engineer",
            "level": "staff",
            "geography": "US",
        }
    )
    api_text = (
        "Acme Labs Staff Backend Engineer in New York, NY. Responsibilities and "
        "requirements for backend services. Apply for this job. "
    ) * 3

    def json_fetcher(url):
        if "greenhouse" in url:
            return {
                "jobs": [
                    {
                        "title": "Staff Backend Engineer",
                        # The requested slug is acmelabs, but this URL belongs to a different board.
                        "absolute_url": "https://job-boards.greenhouse.io/otherco/jobs/123",
                        "location": {"name": "New York, NY"},
                        "content": api_text,
                    }
                ]
            }
        raise LookupError(url)

    result = OfficialJobDiscoveryConnector(
        json_fetcher=json_fetcher,
        text_fetcher=lambda _url: "Loading... Powered by Greenhouse",
    ).collect(
        CollectionRequest(
            source={"source_id": "official_job_discovery", "target": target.as_dict()},
            topic="Acme Labs role",
            run_date="2026-07-14",
            depth="quick",
            max_results=5,
        )
    )

    assert result.rows == []


def test_dynamic_ats_exact_board_path_can_use_rich_api_content_over_js_shell():
    target = ResearchTarget.from_mapping(
        {
            "company": "PostHog",
            "role_family": "software_engineering",
            "role_title": "Site Reliability Engineer Infrastructure",
            "level": "unspecified",
            "geography": "US",
        }
    )
    api_text = (
        "PostHog Site Reliability Engineer Infrastructure, Remote US. Responsibilities "
        "and requirements for production infrastructure. Apply for this job. "
    ) * 3

    def json_fetcher(url):
        if "ashbyhq.com" in url:
            return {
                "jobs": [
                    {
                        "title": "Site Reliability Engineer, Infrastructure",
                        "jobUrl": "https://jobs.ashbyhq.com/posthog/sre",
                        "location": "Remote, US",
                        "descriptionPlain": api_text,
                        "isListed": True,
                    }
                ]
            }
        raise LookupError(url)

    result = OfficialJobDiscoveryConnector(
        json_fetcher=json_fetcher,
        text_fetcher=lambda _url: "Loading... Powered by Ashby",
    ).collect(
        CollectionRequest(
            source={"source_id": "official_job_discovery", "target": target.as_dict()},
            topic="PostHog SRE",
            run_date="2026-07-14",
            depth="quick",
            max_results=5,
        )
    )

    assert len(result.rows) == 1
    assert result.rows[0]["text"] == api_text.strip()
    assert result.rows[0]["is_final_page"] is True
    assert result.rows[0]["ats_ownership_verified"] is True
