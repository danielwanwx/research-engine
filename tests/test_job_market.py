import pytest

from research_engine.job_market import build_job_market_snapshot, normalize_job_scope
from research_engine.runner import build_job_market_snapshot_from_run


SCOPE = {
    "schema_version": "research_scope.v1",
    "profile": "job_market",
    "as_of": "2026-07-16",
    "filters": {
        "geography": ["US"],
        "role_terms": ["AI Engineer"],
        "levels": ["senior"],
        "companies": ["Anthropic", "OpenAI"],
    },
}


def job(evidence_id, url, **extra):
    return {
        "evidence_id": evidence_id,
        "company": "Anthropic",
        "title": "Senior AI Engineer",
        "role_family": "software_engineering",
        "level": "senior",
        "geography": "US",
        "skills": ["Python", "distributed systems"],
        "url": url,
        "canonical_url": url,
        "source_class": "official_jd",
        "current_status": "active",
        "is_final_page": True,
        "content_valid": True,
        "claim_eligible": True,
        "claim_fitness": {"disposition": "accepted", "rejection_reasons": []},
        **extra,
    }


def test_job_scope_is_explicit_and_versioned():
    assert normalize_job_scope(SCOPE)["as_of"] == "2026-07-16"
    without_geography = {
        **SCOPE,
        "filters": {
            key: value for key, value in SCOPE["filters"].items() if key != "geography"
        },
    }
    assert normalize_job_scope(without_geography)["filters"]["geography"] == ["US"]
    with pytest.raises(ValueError, match="explicit research_scope.v1"):
        normalize_job_scope(None)
    with pytest.raises(ValueError, match="job_market"):
        normalize_job_scope({**SCOPE, "profile": "generic"})
    with pytest.raises(ValueError, match="singleton.*role_terms"):
        normalize_job_scope(
            {
                **SCOPE,
                "filters": {
                    **SCOPE["filters"],
                    "role_terms": ["AI Engineer", "ML Engineer"],
                },
            }
        )


def test_snapshot_dedupes_active_roles_and_reconciles_all_rows():
    rows = [
        job(
            "ev-1",
            "https://jobs.example/req-123?utm_source=search",
            requisition_id="req-123",
            compensation={"currency": "USD", "min": 200_000, "max": 250_000},
        ),
        job(
            "ev-2",
            "https://jobs.example/req-123",
            requisition_id="req-123",
        ),
        job("ev-3", "https://jobs.example/closed", current_status="closed"),
        job("ev-4", "https://jobs.example/unknown", current_status="unknown"),
        job(
            "ev-5",
            "https://jobs.example/wrong",
            claim_fitness={"disposition": "rejected", "rejection_reasons": ["wrong_geography"]},
        ),
        job(
            "ev-6",
            "https://jobs.example/search",
            source_class="discovery_only",
            is_final_page=False,
            claim_fitness={"disposition": "discovery_only", "rejection_reasons": ["search_page"]},
        ),
    ]

    snapshot = build_job_market_snapshot(
        rows,
        scope=SCOPE,
        requested_sources=["anthropic", "openai"],
        checked_sources=["anthropic"],
        failed_sources=["openai"],
    )

    assert snapshot["counts"] == {
        "observed": 6,
        "active": 1,
        "closed": 1,
        "duplicate": 1,
        "rejected": 2,
        "unknown_status": 1,
    }
    assert sum(value for key, value in snapshot["counts"].items() if key != "observed") == 6
    assert snapshot["openings"][0]["evidence_ids"] == ["ev-1", "ev-2"]
    assert snapshot["openings"][0]["compensation"]["min"] == 200_000
    assert snapshot["coverage"] == {
        "requested": ["anthropic", "openai"],
        "checked": ["anthropic"],
        "failed": ["openai"],
        "unsupported": [],
        "denominator": 2,
        "checked_count": 1,
    }
    assert snapshot["trend"] is None
    assert snapshot["trend_status"] == "unavailable_without_comparable_prior_snapshot"


def test_unknown_or_rejected_rows_never_count_as_active():
    rows = [
        job("ev-1", "https://jobs.example/landing", is_final_page=False),
        job("ev-2", "https://jobs.example/unknown", current_status="unknown"),
        job("ev-stale", "https://jobs.example/stale", freshness_status="stale"),
        job("ev-geo", "https://jobs.example/unknown-geo", geography=""),
        job(
            "ev-3",
            "https://jobs.example/wrong-company",
            claim_fitness={"disposition": "rejected", "rejection_reasons": ["wrong_company"]},
        ),
    ]

    snapshot = build_job_market_snapshot(rows, scope=SCOPE)

    assert snapshot["counts"]["active"] == 1
    assert snapshot["openings"][0]["canonical_url"].endswith("/stale")
    assert snapshot["rejection_reason_counts"]["not_final_page"] == 1


def test_distinct_official_job_ids_survive_content_duplicate_flags():
    snapshot = build_job_market_snapshot(
        [
            job(
                "ev-1",
                "https://jobs.example/req-1",
                requisition_id="req-1",
                is_duplicate=True,
                claim_eligible=False,
                freshness_status="stale",
                claim_fitness={
                    "disposition": "duplicate",
                    "rejection_reasons": ["duplicate"],
                },
            ),
            job(
                "ev-2",
                "https://jobs.example/req-2",
                requisition_id="req-2",
                is_duplicate=True,
                claim_eligible=False,
                freshness_status="stale",
                claim_fitness={
                    "disposition": "duplicate",
                    "rejection_reasons": ["duplicate"],
                },
            ),
        ],
        scope=SCOPE,
    )

    assert snapshot["counts"]["active"] == 2
    assert snapshot["counts"]["duplicate"] == 0
    assert {opening["job_identity"] for opening in snapshot["openings"]} == {
        "req:req-1",
        "req:req-2",
    }


def test_raw_official_rows_match_scope_and_tracking_urls_dedupe():
    raw = {
        "company": "Anthropic",
        "title": "Senior AI Engineer",
        "location": "San Francisco, CA",
        "skills": ["Python"],
        "source_kind": "official_job_posting",
        "current_status": "active",
        "is_final_page": True,
        "content_valid": True,
        "claim_eligible": True,
    }
    snapshot = build_job_market_snapshot(
        [
            {**raw, "evidence_id": "ev-1", "url": "https://jobs.example/123?utm_source=x"},
            {**raw, "evidence_id": "ev-2", "url": "https://jobs.example/123"},
        ],
        scope=SCOPE,
    )

    assert snapshot["counts"]["active"] == 1
    assert snapshot["counts"]["duplicate"] == 1
    assert snapshot["openings"][0]["evidence_ids"] == ["ev-1", "ev-2"]
    assert snapshot["openings"][0]["field_evidence_ids"]["skills"] == ["ev-1"]


def test_company_coverage_uses_terminal_aggregate_across_repair_passes():
    snapshot = build_job_market_snapshot_from_run(
        [],
        scope=SCOPE,
        execution_report={
            "requests": [
                {
                    "target_company": "Anthropic",
                    "pass_id": "pass-1",
                    "status": "failed",
                },
                {
                    "target_company": "Anthropic",
                    "pass_id": "pass-2",
                    "status": "warning",
                },
                {
                    "target_company": "OpenAI",
                    "pass_id": "pass-1",
                    "status": "failed",
                },
            ]
        },
    )

    assert snapshot["coverage"]["checked"] == ["Anthropic"]
    assert snapshot["coverage"]["failed"] == ["OpenAI"]
    assert not (
        set(snapshot["coverage"]["checked"])
        & set(snapshot["coverage"]["failed"])
    )
