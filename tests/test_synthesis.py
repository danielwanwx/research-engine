from research_engine.packs import select_research_pack
from research_engine.quality import enrich_rows_with_quality
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
        {
            "evidence_id": "ev-0004",
            "connector": "web_page",
            "title": "Buyer price update",
            "url": "https://buyer.example/prices",
            "text": "Contract prices and average selling prices increased QoQ.",
        },
        {
            "evidence_id": "ev-0005",
            "connector": "web_page",
            "title": "Capacity update",
            "url": "https://analyst.example/capacity",
            "text": "Limited supply and capacity constraints remain visible.",
        },
        {
            "evidence_id": "ev-0006",
            "connector": "web_page",
            "title": "Earnings update",
            "url": "https://filing.example/results",
            "text": "Revenue, gross margin, and operating profit improved.",
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


def test_invalid_evidence_cannot_support_claims_or_matrix():
    pack = select_research_pack("DRAM HBM shortage")
    rows = [
        {
            "evidence_id": "ev-invalid",
            "connector": "web_page",
            "title": "Login wall",
            "url": "https://example.com/login",
            "text": (
                "Log in to X. Continue with Google. DRAM contract prices, AI infrastructure, "
                "HBM demand, Micron revenue, gross margin and tight supply."
            ),
            "http_status": 200,
            "content_type": "text/html",
            "final_url": "https://example.com/login",
        }
    ]

    review = build_claim_review(topic="DRAM HBM shortage", pack=pack, rows=rows, warnings=[])
    matrix = build_supply_demand_matrix(topic="DRAM HBM shortage", pack=pack, rows=rows)

    assert review["overall"]["stance"] == "needs_more_evidence"
    assert review["overall"]["confidence"] == "low"
    assert all(claim["evidence_ids"] == [] for claim in review["claims"])
    assert all(row["evidence_ids"] == [] for row in matrix["rows"])


def test_generic_review_excludes_invalid_evidence_ids():
    pack = {"id": "generic", "label": "Generic", "intent": "general_research"}
    rows = [
        {
            "evidence_id": "ev-invalid",
            "connector": "web_page",
            "title": "PDF",
            "url": "https://example.com/report.pdf",
            "text": "",
            "http_status": 200,
            "content_type": "application/pdf",
            "final_url": "https://example.com/report.pdf",
        }
    ]

    review = build_claim_review(topic="generic research", pack=pack, rows=rows, warnings=[])

    assert review["overall"]["stance"] == "no_evidence_collected"
    assert review["claims"][0]["evidence_ids"] == []


def test_platform_search_pages_cannot_support_claims_or_matrix():
    pack = select_research_pack("DRAM HBM shortage")
    rows = [
        {
            "evidence_id": "ev-search",
            "connector": "web_page",
            "source_kind": "platform_search_page",
            "title": "Search results",
            "url": "https://example.com/search?q=dram",
            "text": (
                "DRAM contract prices qoq, tight supply, capacity, HBM demand, "
                "revenue, gross margin, and record operating profit."
            ),
        }
    ]

    review = build_claim_review(topic="DRAM HBM shortage", pack=pack, rows=rows, warnings=[])
    matrix = build_supply_demand_matrix(topic="DRAM HBM shortage", pack=pack, rows=rows)

    assert review["overall"]["stance"] == "needs_more_evidence"
    assert {claim["verdict"] for claim in review["claims"]} == {
        "insufficient_valid_evidence"
    }
    assert all(claim["evidence_ids"] == [] for claim in review["claims"])
    assert all(node["evidence_ids"] == [] for node in matrix["rows"])


def test_distinct_opposing_cited_evidence_calibrates_claim_review():
    pack = select_research_pack("DRAM HBM shortage")
    rows = [
        {
            "evidence_id": "ev-support",
            "connector": "manual",
            "title": "Supplier update",
            "text": (
                "Contract prices rose qoq amid tight supply and HBM capacity constraints. "
                "Revenue and gross margin reached a record."
            ),
        },
        {
            "evidence_id": "ev-oppose",
            "connector": "manual",
            "title": "Buyer update",
            "text": "Oversupply and excess inventory are pushing pricing and revenue lower.",
        },
    ]
    _, quality = enrich_rows_with_quality(rows, topic="DRAM HBM shortage", pack=pack)

    review = build_claim_review(
        topic="DRAM HBM shortage",
        pack=pack,
        rows=rows,
        warnings=[],
        conflict_flags=quality["conflict_flags"],
    )
    brief = build_decision_brief(
        topic="DRAM HBM shortage",
        pack=pack,
        claim_review=review,
        matrix=build_supply_demand_matrix(topic="DRAM HBM shortage", pack=pack, rows=rows),
    )

    assert review["overall"]["stance"] == "conflicted"
    assert review["overall"]["confidence"] == "medium"
    assert review["overall"]["conflict_flag_ids"] == ["availability_pressure"]
    assert brief["action_bias"] == "analyze_before_action"


def test_single_self_conflicting_row_does_not_calibrate_claim_review():
    pack = select_research_pack("DRAM HBM shortage")
    rows = [
        {
            "evidence_id": "ev-both",
            "connector": "manual",
            "title": "Two-sided market update",
            "text": (
                "Contract prices rose qoq while tight supply and oversupply signals coexist. "
                "HBM capacity, revenue, gross margin, and record results remain debated."
            ),
        }
    ]
    _, quality = enrich_rows_with_quality(rows, topic="DRAM HBM shortage", pack=pack)

    review = build_claim_review(
        topic="DRAM HBM shortage",
        pack=pack,
        rows=rows,
        warnings=[],
        conflict_flags=quality["conflict_flags"],
    )

    assert review["overall"]["stance"] == "needs_more_evidence"
    assert review["overall"]["confidence"] == "low"
    assert review["overall"]["conflict_flag_ids"] == []


def test_generic_review_records_independent_support_and_opposition_chains():
    pack = {"id": "generic", "label": "Generic", "intent": "general_research"}
    rows = [
        {
            "evidence_id": "ev-support",
            "url": "https://vendor.example/report",
            "text": "The current evidence supports the stated conclusion.",
            "claim_eligible": True,
            "claim_polarity": "support",
        },
        {
            "evidence_id": "ev-oppose",
            "url": "https://analyst.example/report",
            "text": "Independent current evidence opposes the stated conclusion.",
            "claim_eligible": True,
            "claim_polarity": "oppose",
        },
    ]

    review = build_claim_review(topic="contested conclusion", pack=pack, rows=rows, warnings=[])
    chain = review["claims"][0]["evidence_chains"]

    assert review["overall"]["stance"] == "conflicted"
    assert review["overall"]["confidence"] == "medium"
    assert chain["support_chain"]["evidence_ids"] == ["ev-support"]
    assert chain["opposition_chain"]["evidence_ids"] == ["ev-oppose"]


def test_same_publisher_copies_cannot_produce_supported_high_confidence_claim():
    pack = {
        "id": "corroborated",
        "label": "Corroborated research",
        "intent": "general_research",
        "claim_specs": [
            {
                "claim_id": "claim-1",
                "question": "Is the claim independently corroborated?",
                "keywords": ["confirmed result"],
                "min_evidence": 2,
                "min_independent_support": 2,
            }
        ],
        "decision_rules": {
            "supported_claims_for_supported": 1,
            "supported_claims_for_high_confidence": 1,
        },
    }
    rows = [
        {
            "evidence_id": "ev-1",
            "publisher": "One Publisher",
            "url": "https://one.example/report",
            "text": "The confirmed result was published.",
        },
        {
            "evidence_id": "ev-2",
            "publisher": "One Publisher",
            "url": "https://mirror.example/report",
            "text": "A second copy repeats the confirmed result.",
        },
    ]

    review = build_claim_review(topic="claim", pack=pack, rows=rows, warnings=[])

    assert review["claims"][0]["verdict"] == "needs_more_evidence"
    assert review["claims"][0]["evidence_chains"]["confidence_ceiling"] == "low"
    assert review["overall"]["stance"] == "needs_more_evidence"
    assert review["overall"]["confidence"] == "low"
