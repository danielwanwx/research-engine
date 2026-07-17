from research_engine.packs import select_research_pack
from research_engine.planning import build_query_plan


REQUIRED_FACETS = {
    "technical": {
        "official_docs",
        "repositories",
        "releases",
        "architecture",
        "performance",
        "limitations",
    },
    "market_landscape": {
        "market_definition",
        "companies_products",
        "pricing",
        "demand",
        "competition",
        "constraints",
        "contrary_evidence",
    },
    "job_market": {
        "active_openings",
        "company_coverage",
        "role_terms",
        "geography",
        "skills",
        "compensation",
    },
}


def test_profile_packs_emit_required_facets_and_source_strategy():
    topics = {
        "technical": "distributed inference engine technical architecture",
        "market_landscape": "AI inference market landscape",
        "job_market": "US AI engineer job market",
    }

    for profile, topic in topics.items():
        pack = select_research_pack(topic, pack_id=profile)
        plan = build_query_plan(topic, pack=pack, depth="audit")
        assert set(plan["facets"]) == REQUIRED_FACETS[profile]
        assert all(query["required"] for query in plan["queries"])
        assert all(query["source_types"] for query in plan["queries"])

    technical = build_query_plan(
        topics["technical"],
        pack=select_research_pack(topics["technical"], pack_id="technical"),
        depth="audit",
    )
    assert any("github_public_search" in row["source_types"] for row in technical["queries"])

    jobs = build_query_plan(
        topics["job_market"],
        pack=select_research_pack(topics["job_market"], pack_id="job_market"),
        depth="audit",
    )
    assert any("official_job_discovery" in row["source_types"] for row in jobs["queries"])


def test_nontechnical_topics_do_not_force_github_routing():
    topic = "restaurant lease negotiation"
    pack = select_research_pack(topic)
    plan = build_query_plan(topic, pack=pack, depth="deep")

    assert pack["profile"] == "generic"
    assert plan["profile"] == "generic"
    assert all("github_public_search" not in row["source_types"] for row in plan["queries"])


def test_technical_comparison_emits_per_project_repository_facets():
    topic = "vLLM versus SGLang inference engines"
    plan = build_query_plan(topic, pack=select_research_pack(topic), depth="deep")

    assert {"project_vllm_repository", "project_sglang_repository"}.issubset(plan["facets"])
    repository_queries = [
        row for row in plan["queries"] if "github_public_search" in row["source_types"]
    ]
    assert [row["query"] for row in repository_queries] == ["vLLM in:name", "SGLang in:name"]


def test_market_scope_context_is_preserved_when_available():
    topic = "AI inference market landscape"
    plan = build_query_plan(
        topic,
        pack=select_research_pack(topic, pack_id="market_landscape"),
        depth="audit",
        scope={
            "schema_version": "research_scope.v1",
            "profile": "market_landscape",
            "as_of": "2026-07-16",
            "filters": {
                "geography": ["US"],
                "definition": ["hosted AI inference platforms"],
            },
        },
    )

    assert plan["claim_context"] == {
        "as_of": "2026-07-16",
        "definition": ["hosted AI inference platforms"],
        "geography": ["US"],
    }


def test_job_quantitative_claims_require_explicit_scope():
    topic = "AI engineer job market"
    pack = select_research_pack(topic, pack_id="job_market")

    unscoped = build_query_plan(topic, pack=pack, depth="audit")
    assert unscoped["quantitative_claims_allowed"] is False

    scoped = build_query_plan(
        topic,
        pack=pack,
        depth="audit",
        scope={
            "schema_version": "research_scope.v1",
            "profile": "job_market",
            "as_of": "2026-07-16",
            "filters": {
                "geography": ["US"],
                "role_terms": ["AI Engineer"],
                "levels": ["senior"],
                "companies": ["Anthropic", "OpenAI"],
            },
        },
    )
    assert scoped["quantitative_claims_allowed"] is True
    assert scoped["scope"]["profile"] == "job_market"
    assert scoped["job_company_coverage"] == {
        "requested": ["Anthropic", "OpenAI"],
        "planned": ["Anthropic", "OpenAI"],
        "unsupported_by_depth_budget": [],
    }


def test_job_company_coverage_exposes_depth_budget_overflow():
    topic = "AI engineer job market"
    companies = [f"Company {index}" for index in range(1, 8)]
    plan = build_query_plan(
        topic,
        pack=select_research_pack(topic, pack_id="job_market"),
        depth="quick",
        scope={
            "schema_version": "research_scope.v1",
            "profile": "job_market",
            "as_of": "2026-07-16",
            "filters": {
                "geography": ["US"],
                "role_terms": ["AI Engineer"],
                "levels": ["senior"],
                "companies": companies,
            },
        },
    )

    assert plan["job_company_coverage"] == {
        "requested": companies,
        "planned": companies[:5],
        "unsupported_by_depth_budget": companies[5:],
    }
