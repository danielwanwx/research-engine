import pytest

from research_engine.packs import select_research_pack
from research_engine.planning import (
    DEPTH_BUDGETS,
    build_query_plan,
    collection_requests_from_plan,
    route_profile,
    validate_research_scope,
)


def test_profile_routing_prefers_scope_then_pack():
    assert route_profile(scope={"profile": "job_market"}, pack={"profile": "technical"}) == "job_market"
    assert route_profile(pack={"profile": "market-landscape"}) == "market_landscape"
    assert route_profile(pack={"intent": "technical_research"}) == "technical"
    assert route_profile(pack={"id": "generic"}) == "generic"


def test_legacy_query_templates_normalize_to_deterministic_facets():
    pack = {
        "profile": "technical",
        "query_templates": [
            {"tier": "official_docs", "template": "{topic} official docs"},
            {"tier": "official_docs", "template": "{topic} architecture"},
        ],
    }

    first = build_query_plan("vLLM", pack=pack, depth="deep")
    second = build_query_plan("vLLM", pack=pack, depth="deep")

    assert first == second
    assert [item["query_id"] for item in first["queries"]] == ["q-0001", "q-0002"]
    assert all(item["facet_id"] == "official_docs" for item in first["queries"])
    assert all("{topic}" not in item["query"] for item in first["queries"])


def test_explicit_profile_scope_does_not_inherit_generic_pack_templates():
    plan = build_query_plan(
        "vLLM versus SGLang",
        pack={
            "profile": "generic",
            "query_templates": [{"tier": "legacy", "template": "{topic}"}],
        },
        scope={
            "schema_version": "research_scope.v1",
            "profile": "technical",
            "filters": {},
        },
        depth="deep",
    )

    assert plan["profile"] == "technical"
    assert {"project_vllm_repository", "project_sglang_repository"}.issubset(plan["facets"])
    assert sum("github_public_search" in item["source_types"] for item in plan["queries"]) == 2


@pytest.mark.parametrize("depth", ["quick", "deep", "audit"])
def test_query_plan_never_exceeds_depth_budgets(depth):
    pack = {
        "profile": "generic",
        "query_templates": [
            {"tier": f"facet-{index}", "template": f"{{topic}} term {index}"}
            for index in range(20)
        ],
    }

    plan = build_query_plan("bounded research", pack=pack, depth=depth)

    budget = DEPTH_BUDGETS[depth]
    assert len(plan["queries"]) <= budget["max_queries"]
    assert all(item["max_results"] <= budget["max_results_per_query"] for item in plan["queries"])
    assert plan["budget"]["max_canonical_refetches"] <= budget["max_canonical_refetches"]


def test_quick_plan_discloses_required_facets_omitted_by_budget():
    pack = select_research_pack("restaurant lease negotiation", pack_id="generic")

    plan = build_query_plan("restaurant lease negotiation", pack=pack, depth="quick")

    assert plan["required_facets"] == [
        "overview",
        "primary_sources",
        "current_evidence",
        "alternatives",
        "risks",
    ]
    assert plan["facets"] == ["overview", "primary_sources", "current_evidence"]
    assert plan["omitted_required_facets"] == ["alternatives", "risks"]


def test_scope_validation_accepts_complete_job_scope_and_rejects_ambiguous_scope():
    scope = validate_research_scope(
        {
            "schema_version": "research_scope.v1",
            "profile": "job_market",
            "as_of": "2026-07-16",
            "filters": {
                "geography": ["US"],
                "role_terms": ["AI Engineer"],
                "levels": ["senior"],
                "companies": ["matrix"],
            },
        }
    )
    assert scope["profile"] == "job_market"
    assert scope["quantitative_axis_policy"] == {
        "companies": "bounded_multi",
        "geography": "singleton",
        "levels": "singleton",
        "role_terms": "singleton",
    }

    with pytest.raises(ValueError, match="job_market scope requires"):
        validate_research_scope(
            {
                "schema_version": "research_scope.v1",
                "profile": "job_market",
                "filters": {"geography": ["US"]},
            }
        )


@pytest.mark.parametrize("axis", ["geography", "role_terms", "levels"])
def test_quantitative_job_scope_rejects_multi_valued_non_company_axes(axis):
    filters = {
        "geography": ["US"],
        "role_terms": ["AI Engineer"],
        "levels": ["senior"],
        "companies": ["Anthropic", "OpenAI"],
    }
    filters[axis] = [*filters[axis], "second value"]

    with pytest.raises(ValueError, match=f"singleton.*{axis}"):
        validate_research_scope(
            {
                "schema_version": "research_scope.v1",
                "profile": "job_market",
                "as_of": "2026-07-16",
                "filters": filters,
            }
        )


def test_planned_ids_propagate_to_collection_requests():
    plan = build_query_plan(
        "JSON Canvas adopters",
        pack={
            "profile": "generic",
            "query_templates": [{"tier": "adopters", "template": "{topic}"}],
        },
        depth="quick",
        search_provider="searxng",
        search_endpoint="https://search.example.org/search",
    )

    requests = collection_requests_from_plan(plan, topic="JSON Canvas adopters", run_date="2026-07-16")

    assert len(requests) == 1
    assert requests[0].source["query_id"] == "q-0001"
    assert requests[0].source["facet_id"] == "adopters"
    assert requests[0].source["provider"] == "searxng"
    assert requests[0].source["endpoint"] == "https://search.example.org/search"
    assert requests[0].source["connector"] == "web_search"
