from research_engine.relevance import (
    build_facet_coverage,
    build_relevance_preview,
    rank_github_repositories,
    score_row_relevance,
)
from research_engine.packs import select_research_pack
from research_engine.planning import build_query_plan


def repository(
    name,
    description,
    *,
    stars=0,
    archived=False,
    raw_rank=1,
    updated="2026-07-01T00:00:00Z",
):
    return {
        "title": name,
        "text": description,
        "topics": [],
        "archived": archived,
        "updated_at": updated,
        "raw_api_rank": raw_rank,
        "metrics": {"stars": stars, "forks": 0},
    }


def test_topical_canonical_repository_outranks_updated_noise():
    rows = [
        repository("fresh/noise", "Daily weather dashboard", stars=0, raw_rank=1),
        repository(
            "vllm-project/vllm",
            "A high-throughput and memory-efficient inference engine for LLMs",
            stars=50000,
            raw_rank=2,
        ),
    ]

    ranked = rank_github_repositories(rows, "vLLM LLM inference engine")

    assert ranked[0]["title"] == "vllm-project/vllm"
    assert ranked[0]["engine_rank"] == 1
    assert ranked[0]["raw_api_rank"] == 2


def test_archived_repository_receives_penalty():
    rows = [
        repository("org/live", "research agent framework", stars=20, raw_rank=2),
        repository("org/archived", "research agent framework", stars=20, archived=True, raw_rank=1),
    ]

    ranked = rank_github_repositories(rows, "research agent framework")

    assert ranked[0]["title"] == "org/live"
    assert ranked[0]["ranking_components"]["archived_penalty"] == 0.0
    assert ranked[1]["ranking_components"]["archived_penalty"] < 0.0


def test_stars_cannot_override_topical_mismatch():
    rows = [
        repository("famous/unrelated", "Operating system kernel", stars=2_000_000),
        repository("small/relevant", "JSON Canvas open specification", stars=1, raw_rank=2),
    ]

    ranked = rank_github_repositories(rows, "JSON Canvas specification")

    assert ranked[0]["title"] == "small/relevant"
    assert ranked[0]["relevance_score"] > ranked[1]["relevance_score"]


def test_row_relevance_is_separate_and_components_are_inspectable():
    scored = score_row_relevance(
        {
            "title": "JSON Canvas specification",
            "text": "Open format for infinite canvas documents",
            "publisher": "Obsidian",
            "facet_id": "official_spec",
        },
        "JSON Canvas open specification",
    )

    assert 0 < scored["relevance_score"] <= 1
    assert set(scored["relevance_components"]) == {"title", "body", "entity", "facet"}
    assert "quality_score" not in scored


def test_preview_diversity_and_facet_coverage_are_honest():
    rows = [
        {
            "evidence_id": "ev-1",
            "facet_id": "spec",
            "url": "https://one.example/spec",
            "publisher": "One",
            "claim_eligible": True,
            "relevance_score": 0.9,
            "quality_score": 0.7,
        },
        {
            "evidence_id": "ev-2",
            "facet_id": "spec",
            "url": "https://one.example/copy",
            "publisher": "One",
            "claim_eligible": True,
            "relevance_score": 0.8,
            "quality_score": 0.9,
        },
        {
            "evidence_id": "ev-3",
            "facet_id": "adopters",
            "url": "https://two.example/app",
            "publisher": "Two",
            "claim_eligible": True,
            "relevance_score": 0.7,
            "quality_score": 0.7,
        },
    ]
    plan = {
        "queries": [
            {"facet_id": "spec", "required": True},
            {"facet_id": "adopters", "required": True},
            {"facet_id": "risks", "required": True},
        ]
    }

    preview = build_relevance_preview(rows, limit=10)
    coverage = build_facet_coverage(rows, query_plan=plan)

    assert [row["evidence_id"] for row in preview] == ["ev-1", "ev-3"]
    assert coverage["missing_required_facets"] == ["risks"]
    assert coverage["required_facets_covered"] == 2


def test_facet_coverage_includes_required_facets_omitted_by_depth_budget():
    topic = "restaurant lease negotiation"
    plan = build_query_plan(
        topic,
        pack=select_research_pack(topic, pack_id="generic"),
        depth="quick",
    )

    coverage = build_facet_coverage([], query_plan=plan)

    assert coverage["required_facets"] == 5
    assert coverage["required_facets_covered"] == 0
    assert coverage["missing_required_facets"] == plan["required_facets"]
    assert coverage["omitted_required_facets"] == ["alternatives", "risks"]
    omitted = {
        row["facet_id"]: row
        for row in coverage["facets"]
        if row["facet_id"] in coverage["omitted_required_facets"]
    }
    assert all(row["status"] == "omitted_by_budget" for row in omitted.values())
    assert all(row["query_ids"] == [] for row in omitted.values())
