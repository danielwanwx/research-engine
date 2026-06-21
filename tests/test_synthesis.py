from research_engine.packs import select_research_pack
from research_engine.synthesis import (
    build_claim_review,
    build_decision_brief,
    build_supply_demand_matrix,
)


def test_pack_claims_and_matrix_score_evidence():
    pack = select_research_pack("DRAM HBM shortage")
    rows = [
        {
            "evidence_id": "ev-0001",
            "connector": "web_page",
            "title": "Contract prices rise",
            "url": "https://example.com/prices",
            "text": "DRAM contract prices and ASP are rising QoQ due to tight supply.",
        },
        {
            "evidence_id": "ev-0002",
            "connector": "web_page",
            "title": "AI infrastructure demand",
            "url": "https://example.com/ai",
            "text": "AI infrastructure and data center HBM demand increase compute capacity needs.",
        },
        {
            "evidence_id": "ev-0003",
            "connector": "web_page",
            "title": "Supplier leverage",
            "url": "https://example.com/margin",
            "text": "Micron revenue, gross margin, and operating profit improved.",
        },
    ]

    review = build_claim_review(topic="DRAM HBM shortage", pack=pack, rows=rows, warnings=[])
    matrix = build_supply_demand_matrix(topic="DRAM HBM shortage", pack=pack, rows=rows)
    brief = build_decision_brief(
        topic="DRAM HBM shortage",
        pack=pack,
        claim_review=review,
        matrix=matrix,
    )

    assert review["overall"]["stance"] == "supported"
    assert review["overall"]["confidence"] == "high"
    assert matrix["summary"]["gap_assessment"] == "demand_outpacing_near_term_supply"
    assert brief["action_bias"] == "constructive_but_verify_price_and_valuation"
    assert brief["not_investment_advice"] is True
    assert brief["not_professional_advice"] is True


def test_generic_decision_brief_is_not_marked_as_investment_advice():
    pack = {"id": "generic", "label": "Generic", "intent": "general_research"}
    review = build_claim_review(topic="restaurant lease research", pack=pack, rows=[], warnings=[])
    matrix = build_supply_demand_matrix(topic="restaurant lease research", pack=pack, rows=[])
    brief = build_decision_brief(
        topic="restaurant lease research",
        pack=pack,
        claim_review=review,
        matrix=matrix,
    )

    assert brief["not_investment_advice"] is False
    assert brief["not_professional_advice"] is True
