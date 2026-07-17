from research_engine.repair import build_repair_plan, progress_fingerprint
from research_engine.runner import build_repair_failures, build_repair_requests


FACETS = [
    {
        "facet_id": "overview",
        "query": "JSON Canvas open file format specification adoption",
        "source_types": [],
        "required": True,
        "freshness_window_days": 365,
        "max_results": 8,
    },
    {
        "facet_id": "optional-history",
        "query": "JSON Canvas history",
        "source_types": ["web_search"],
        "required": False,
        "max_results": 5,
    },
]


def test_only_failed_required_facets_are_repaired_and_constraints_survive():
    plan = build_repair_plan(
        FACETS,
        [
            {"facet_id": "overview", "reason": "no_executable_sources"},
            {"facet_id": "optional-history", "reason": "no_relevant_evidence"},
        ],
        as_of="2026-07-16",
        search_enabled=True,
    )

    assert plan["should_repair"] is True
    assert [facet["facet_id"] for facet in plan["facets"]] == ["overview"]
    repaired = plan["facets"][0]
    assert repaired["source_types"] == ["web_search"]
    assert repaired["freshness_window_days"] == 365
    assert repaired["max_results"] == 8
    assert repaired["repair_reason"] == "no_executable_sources"


def test_failure_reasons_map_to_bounded_query_changes():
    failures = [
        ("no_relevant_evidence", "JSON Canvas open file format specification adoption"),
        ("freshness_failure", "memory prices"),
        ("source_concentration", "inference market"),
    ]

    queries = []
    for reason, query in failures:
        plan = build_repair_plan(
            [{"facet_id": "f", "query": query, "source_types": ["web_search"], "required": True}],
            [{"facet_id": "f", "reason": reason}],
            as_of="2026-07-16",
        )
        queries.append(plan["facets"][0]["query"])

    assert queries[0] == "JSON Canvas specification"
    assert queries[1] == "memory prices current 2026"
    assert queries[2] == "inference market official independent"


def test_long_repair_queries_keep_time_role_company_and_record_constraints():
    query = (
        "United States backend software engineer employment market trend "
        "January 2026 through July 2026 Anthropic OpenAI"
    )
    constraints = ["backend software engineer", "Anthropic", "OpenAI", "2026"]
    plan = build_repair_plan(
        [
            {
                "facet_id": "trend",
                "query": query,
                "source_types": ["web_search"],
                "required": True,
                "repair_constraints": constraints,
            }
        ],
        [{"facet_id": "trend", "reason": "no_relevant_evidence"}],
        as_of="2026-07-16",
    )

    repaired = plan["facets"][0]
    assert repaired["query"] == query
    assert repaired["original_query"] == query
    assert repaired["inherited_constraints"] == constraints


def test_refetch_repair_uses_only_next_bounded_candidates():
    plan = build_repair_plan(
        [{"facet_id": "f", "query": "topic", "required": True}],
        [
            {
                "facet_id": "f",
                "reason": "canonical_refetch_failure",
                "next_candidate_urls": ["https://a.example/2", "https://b.example/3"],
            }
        ],
        as_of="2026-07-16",
        max_refetch_candidates=1,
    )

    assert plan["facets"][0]["candidate_urls"] == ["https://a.example/2"]


def test_future_dated_only_yield_triggers_freshness_repair():
    query_plan = {
        "profile": "generic",
        "queries": [
            {
                "query_id": "q-0001",
                "facet_id": "current_evidence",
                "required": True,
                "freshness_window_days": 30,
            }
        ],
    }
    failures = build_repair_failures(
        query_plan=query_plan,
        rows=[
            {
                "evidence_id": "ev-future",
                "connector": "web_page",
                "source_class": "canonical_content",
                "query_id": "q-0001",
                "facet_id": "current_evidence",
                "freshness_status": "future_dated",
                "claim_eligible": False,
            }
        ],
        execution_report={
            "requests": [
                {
                    "query_id": "q-0001",
                    "facet_id": "current_evidence",
                    "pass_id": "pass-1",
                    "status": "ok",
                }
            ]
        },
        quality_report={
            "facet_coverage": {
                "facets": [
                    {"facet_id": "current_evidence", "evidence_ids": ["placeholder"]}
                ]
            }
        },
    )

    assert {failure["reason"] for failure in failures} == {"freshness_failure"}


def test_multiple_failures_for_one_facet_combine_into_one_repair():
    plan = build_repair_plan(
        [{"facet_id": "f", "query": "memory prices", "required": True}],
        [
            {"facet_id": "f", "reason": "freshness_failure"},
            {"facet_id": "f", "reason": "source_concentration"},
        ],
        as_of="2026-07-16",
    )

    assert len(plan["facets"]) == 1
    assert plan["facets"][0]["repair_reasons"] == [
        "freshness_failure",
        "source_concentration",
    ]
    assert plan["facets"][0]["query"] == "memory prices current 2026 official independent"


def test_progress_fingerprint_and_one_pass_stop_are_deterministic():
    rows = [{"canonical_url": "https://example.com/a", "freshness_status": "fresh"}]
    failures = [{"facet_id": "f", "reason": "no_relevant_evidence"}]
    fingerprint = progress_fingerprint(rows, failures)
    assert fingerprint == progress_fingerprint(list(reversed(rows)), list(reversed(failures)))

    stopped = build_repair_plan(
        FACETS,
        failures,
        as_of="2026-07-16",
        previous_progress_fingerprint=fingerprint,
        current_progress_fingerprint=fingerprint,
    )
    assert stopped["should_repair"] is False
    assert stopped["stop_reason"] == "repair_no_progress"

    limited = build_repair_plan(FACETS, failures, as_of="2026-07-16", pass_number=2)
    assert limited["should_repair"] is False
    assert limited["stop_reason"] == "repair_limit_reached"


def test_unavailable_search_does_not_emit_an_unchanged_repair():
    stopped = build_repair_plan(
        FACETS,
        [
            {"facet_id": "overview", "reason": "ignored_reason"},
            {"facet_id": "overview", "reason": "no_executable_sources"},
        ],
        as_of="2026-07-16",
        search_enabled=False,
    )

    assert stopped["should_repair"] is False
    assert stopped["stop_reason"] == "repair_unavailable"


def test_failed_canonical_lineage_repairs_next_candidate_with_direct_web_fetch():
    query = {
        "facet_id": "overview",
        "query_id": "q-0001",
        "query": "JSON Canvas overview",
        "source_types": ["web_search"],
        "required": True,
        "freshness_window_days": None,
        "max_results": 5,
    }
    query_plan = {
        "profile": "generic",
        "depth": "quick",
        "search_provider": "anysearch",
        "queries": [query],
    }
    rows = [
        {
            "evidence_id": "ev-search-1",
            "connector": "web_search",
            "source_class": "discovery_only",
            "facet_id": "overview",
            "query_id": "q-0001",
            "url": "https://broken.example/first",
            "discovery_source_id": "search:q-0001:1",
            "claim_eligible": False,
        },
        {
            "evidence_id": "ev-search-2",
            "connector": "web_search",
            "source_class": "discovery_only",
            "facet_id": "overview",
            "query_id": "q-0001",
            "url": "https://working.example/second",
            "claim_eligible": False,
        },
        {
            "evidence_id": "ev-search-duplicate",
            "connector": "web_search",
            "source_class": "discovery_only",
            "facet_id": "overview",
            "query_id": "q-0001",
            "url": "https://broken.example/first",
            "claim_eligible": False,
        },
        {
            "evidence_id": "ev-page-1",
            "connector": "web_page",
            "source_class": "canonical_content",
            "facet_id": "overview",
            "query_id": "q-0001",
            "url": "https://broken.example/first",
            "discovery_source_id": "search:q-0001:1",
            "content_valid": False,
            "claim_eligible": False,
        },
    ]
    failures = build_repair_failures(
        query_plan=query_plan,
        rows=rows,
        execution_report={
            "requests": [
                {
                    "query_id": "q-0001",
                    "facet_id": "overview",
                    "pass_id": "pass-1",
                    "status": "ok",
                }
            ]
        },
        quality_report={
            "facet_coverage": {
                "facets": [{"facet_id": "overview", "evidence_ids": ["placeholder"]}]
            }
        },
    )

    canonical_failure = next(
        failure for failure in failures if failure["reason"] == "canonical_refetch_failure"
    )
    assert canonical_failure["failed_discovery_source_ids"] == ["search:q-0001:1"]
    assert canonical_failure["next_candidate_urls"] == ["https://working.example/second"]

    repair_plan = build_repair_plan(
        [query],
        failures,
        as_of="2026-07-16",
        max_refetch_candidates=1,
    )
    requests = build_repair_requests(
        query_plan,
        repair_plan=repair_plan,
        topic="JSON Canvas",
        run_date="2026-07-16",
    )

    assert len(requests) == 1
    assert requests[0].source["connector"] == "web_page"
    assert requests[0].source["pass_id"] == "pass-2"
    assert [page["url"] for page in requests[0].source["pages"]] == [
        "https://working.example/second"
    ]
