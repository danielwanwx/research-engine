import json
from pathlib import Path

import pytest

from research_engine.packs import (
    build_pack_queries,
    load_research_packs,
    pack_summary,
    select_research_pack,
)


def test_load_and_select_default_packs():
    packs = load_research_packs()
    ids = {pack["id"] for pack in packs}

    assert {
        "generic",
        "interview_prep",
        "job_market",
        "market_landscape",
        "memory_cycle",
        "technical",
    } <= ids
    assert select_research_pack("DRAM HBM shortage")["id"] == "memory_cycle"
    assert select_research_pack("restaurant lease negotiation")["id"] == "generic"


def test_interview_prep_pack_selects_and_builds_interview_queries():
    pack = select_research_pack("OpenAI SWE AI Platform interview loop", pack_id="interview_prep")
    assert pack["intent"] == "interview_target_research"

    auto = select_research_pack("Anthropic research engineer interview process")
    assert auto["id"] == "interview_prep"

    queries = build_pack_queries("OpenAI SWE AI Platform", pack)
    tiers = {query["tier"] for query in queries}
    assert {"process", "rubric", "role_depth"} <= tiers
    assert all("{topic}" not in query["query"] for query in queries)
    assert any("interview" in query["query"].lower() for query in queries)


def test_empty_cwd_packs_does_not_mask_package_defaults(tmp_path, monkeypatch):
    (tmp_path / "packs").mkdir()
    monkeypatch.chdir(tmp_path)

    assert select_research_pack("DRAM HBM shortage")["id"] == "memory_cycle"


def test_pack_summary_and_queries_are_template_driven():
    pack = select_research_pack("DRAM HBM shortage")
    queries = build_pack_queries("DRAM HBM shortage", pack)

    assert pack_summary(pack)["intent"] == "financial_market_research"
    assert any(query["tier"] == "official_ir" for query in queries)
    assert all("{topic}" not in query["query"] for query in queries)


def test_generic_pack_uses_the_approved_five_facet_contract():
    pack = select_research_pack("restaurant lease negotiation", pack_id="generic")

    assert [facet["id"] for facet in pack["facets"]] == [
        "overview",
        "primary_sources",
        "current_evidence",
        "alternatives",
        "risks",
    ]


def test_project_packs_match_packaged_defaults():
    project_root = Path(__file__).resolve().parents[1]
    project_pack_dir = project_root / "packs"
    package_pack_dir = project_root / "src/research_engine/default_packs"

    for project_pack in project_pack_dir.glob("*.json"):
        packaged_pack = package_pack_dir / project_pack.name
        assert packaged_pack.exists(), f"missing packaged default pack: {project_pack.name}"
        assert json.loads(project_pack.read_text(encoding="utf-8")) == json.loads(
            packaged_pack.read_text(encoding="utf-8")
        )


def test_profile_packs_route_only_on_explicit_domain_intent():
    assert select_research_pack("vLLM vs SGLang technical architecture")["id"] == "technical"
    assert select_research_pack("AI inference vendor market landscape pricing")["id"] == (
        "market_landscape"
    )
    assert select_research_pack("US AI engineer job market openings")["id"] == "job_market"
    assert select_research_pack("AI engineering hiring market")["id"] == "job_market"
    assert select_research_pack("US software engineer employment market and hiring trend")[
        "id"
    ] == "job_market"
    assert select_research_pack("restaurant lease negotiation")["id"] == "generic"
    assert select_research_pack("Anthropic engineer interview hiring bar")["id"] == (
        "interview_prep"
    )


def test_invalid_profile_overlay_is_rejected(tmp_path):
    (tmp_path / "technical.json").write_text(
        json.dumps(
            {
                "id": "technical",
                "profile": "technical",
                "facets": [
                    {
                        "id": "official_docs",
                        "query_templates": ["{topic} docs"],
                        "source_types": ["web_search"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="technical pack missing required facets"):
        load_research_packs(tmp_path)
