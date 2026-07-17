from research_engine.loop import build_loop_contract, build_loop_record


def base_loop_kwargs(**overrides):
    payload = {
        "topic": "AI capex sustainability",
        "status": "complete",
        "dry_run": False,
        "rows": [{"evidence_id": "ev-0001", "title": "source"}],
        "warnings": [],
        "query_plan": {
            "max_results_per_source": 3,
            "sources": [{"source_id": "external", "connector": "external_jsonl"}],
        },
        "execution_report": {
            "max_workers": 4,
            "retries": 1,
            "source_timeout_seconds": 10,
        },
        "quality_report": {
            "average_quality_score": 0.7,
            "duplicate_cluster_count": 0,
            "conflict_flags": [],
        },
        "claim_review": {
            "overall": {
                "stance": "supported",
                "confidence": "medium",
            }
        },
        "decision_brief": {"action_bias": "analyze_before_action"},
    }
    payload.update(overrides)
    return payload


def test_generic_evidence_requires_analysis_before_decision_ready():
    record = build_loop_record(
        **base_loop_kwargs(
            claim_review={
                "overall": {
                    "stance": "evidence_collected_needs_analysis",
                    "confidence": "medium",
                }
            }
        )
    )

    assert record["loop_status"] == "complete_with_review_required"
    assert record["stop_reason"] == "completed_with_review_required"
    assert any(action["reason"] == "claim_grounding" for action in record["feedback_actions"])


def test_unproven_or_conflicted_claims_require_review():
    for stance in ("needs_more_evidence", "conflicted"):
        record = build_loop_record(
            **base_loop_kwargs(
                claim_review={"overall": {"stance": stance, "confidence": "medium"}}
            )
        )

        claim_grounding = next(
            result
            for result in record["check_results"]
            if result["check_id"] == "claim_grounding"
        )
        assert claim_grounding["status"] == "warn"
        assert record["loop_status"] == "complete_with_review_required"


def test_loop_record_includes_domain_agent_loop_requirements():
    record = build_loop_record(**base_loop_kwargs())

    check_ids = {result["check_id"] for result in record["check_results"]}

    assert {
        "context_hygiene",
        "stop_brakes",
        "critic_separation",
        "tool_focus",
    }.issubset(check_ids)
    assert record["loop_status"] == "complete"
    assert record["stop_reason"] == "acceptance_checks_passed"


def test_sensitive_artifact_fields_block_loop():
    record = build_loop_record(
        **base_loop_kwargs(
            rows=[
                {
                    "evidence_id": "ev-0001",
                    "title": "logged-in capture",
                    "metadata": {"cookie": "session=secret"},
                }
            ]
        )
    )

    assert record["loop_status"] == "blocked"
    assert record["stop_reason"] == "critical_check_failed:context_hygiene"
    assert any(action["reason"] == "context_hygiene" for action in record["feedback_actions"])


def test_sensitive_artifact_string_values_block_loop():
    record = build_loop_record(
        **base_loop_kwargs(
            rows=[
                {
                    "evidence_id": "ev-0001",
                    "title": "logged-in capture",
                    "text": "Visible evidence Cookie: sessionid=session-secret",
                }
            ]
        )
    )

    assert record["loop_status"] == "blocked"
    assert record["stop_reason"] == "critical_check_failed:context_hygiene"
    assert any(action["reason"] == "context_hygiene" for action in record["feedback_actions"])


def test_duplicate_source_ids_are_tool_focus_warning():
    record = build_loop_record(
        **base_loop_kwargs(
            query_plan={
                "max_results_per_source": 3,
                "sources": [
                    {"source_id": "forum_search", "connector": "agent_reach_bridge"},
                    {"source_id": "forum_search", "connector": "external_jsonl"},
                ],
            }
        )
    )

    tool_focus = next(
        result for result in record["check_results"] if result["check_id"] == "tool_focus"
    )

    assert tool_focus["status"] == "warn"
    assert record["loop_status"] == "complete_with_review_required"
    assert any(action["reason"] == "tool_focus" for action in record["feedback_actions"])


def test_loop_contract_exposes_domain_agent_contract():
    contract = build_loop_contract(
        topic="medical billing denial trend",
        pack={"id": "generic", "intent": "domain_research"},
        query_plan={
            "depth": "quick",
            "platform_scope": "broad",
            "collection_modes": {},
            "max_results_per_source": 3,
            "sources": [{"source_id": "payer_policy", "connector": "web_page"}],
        },
        dry_run=False,
        execution_options={
            "max_workers": 4,
            "retries": 1,
            "source_timeout_seconds": 10,
        },
    )

    assert "medical_billing_coding" in contract["domain_agent_contract"]["downstream_domains"]
    assert {check["id"] for check in contract["checks"]}.issuperset(
        {"context_hygiene", "stop_brakes", "critic_separation", "tool_focus"}
    )
