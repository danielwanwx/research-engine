from research_engine.conflicts import build_claim_chains, build_independence_key


def evidence(evidence_id, host, polarity, **extra):
    return {
        "evidence_id": evidence_id,
        "url": f"https://{host}/article",
        "text": f"Evidence {evidence_id} with enough meaningful content for review.",
        "content_valid": True,
        "claim_eligible": True,
        "claim_polarity": polarity,
        **extra,
    }


def test_independence_key_prefers_explicit_family_and_repository():
    assert build_independence_key(
        {"source_family": "Reuters", "url": "https://example.com/copy"}
    ) == "family:reuters"
    assert build_independence_key(
        {"url": "https://github.com/vllm-project/vllm/issues/1"}
    ) == "repo:github.com/vllm-project/vllm"
    assert build_independence_key({"url": "https://www.example.com/report"}) == "host:example.com"
    assert build_independence_key({"publisher": "The Verge"}) == "publisher:the-verge"


def test_two_independent_supporting_rows_satisfy_corroboration():
    review = build_claim_chains(
        [
            evidence("ev-1", "vendor.example", "support"),
            evidence("ev-2", "analyst.example", "support"),
        ],
        claim_id="claim-1",
        min_support=2,
    )

    assert review["stance"] == "supported"
    assert review["confidence_ceiling"] == "high"
    assert review["support_chain"]["independent_source_count"] == 2


def test_independent_opposition_conflicts_but_duplicates_do_not_count():
    duplicate_text_hash = "same-content"
    rows = [
        evidence("ev-1", "vendor.example", "support", content_hash=duplicate_text_hash),
        evidence(
            "ev-2",
            "vendor-copy.example",
            "support",
            source_family="Vendor",
            content_hash=duplicate_text_hash,
        ),
        evidence("ev-3", "critic.example", "oppose"),
        evidence("ev-4", "search.example", "oppose", source_class="discovery_only"),
    ]

    review = build_claim_chains(rows, claim_id="claim-1", min_support=2)

    assert review["stance"] == "conflicted"
    assert review["confidence_ceiling"] == "medium"
    assert review["support_chain"]["evidence_ids"] == ["ev-1"]
    assert review["opposition_chain"]["evidence_ids"] == ["ev-3"]


def test_same_family_and_self_conflict_do_not_form_independent_chains():
    rows = [
        evidence("ev-self", "one.example", "support", source_family="owner"),
        evidence("ev-self", "two.example", "oppose", source_family="owner"),
        evidence("ev-copy", "copy.example", "oppose", source_family="owner"),
    ]

    review = build_claim_chains(rows, claim_id="claim-1", min_support=2)

    assert review["stance"] == "needs_more_evidence"
    assert review["confidence_ceiling"] == "low"
    assert review["opposition_chain"]["independent_source_count"] == 0
