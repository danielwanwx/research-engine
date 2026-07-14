"""Loop-engineering contracts and records for research runs."""

from __future__ import annotations

from typing import Any

from research_engine.models import utc_now
from research_engine.security import sensitive_paths, sensitive_value_paths


QUALITY_PASS_THRESHOLD = 0.55
REPORT_EVIDENCE_PREVIEW_LIMIT = 20
FOCUSED_CONNECTOR_LIMIT = 6
FOCUSED_SOURCE_LIMIT = 12


def build_loop_contract(
    *,
    topic: str,
    pack: dict[str, Any],
    query_plan: dict[str, Any],
    dry_run: bool,
    execution_options: dict[str, Any],
) -> dict[str, Any]:
    """Build the inspectable loop contract for a research run."""

    sources = query_plan.get("sources") or []
    return {
        "generated_at": utc_now(),
        "loop_id": "research_loop_v1",
        "goal": (
            "Collect traceable evidence for the topic, check source quality and conflicts, "
            "then stop with auditable artifacts before any LLM synthesis."
        ),
        "input_scope": {
            "topic": topic,
            "artifact_contract": query_plan.get("artifact_contract"),
            "target": query_plan.get("target"),
            "pack": {
                "id": str(pack.get("id") or "generic"),
                "profile": str(pack.get("profile") or pack.get("id") or "generic"),
                "intent": str(pack.get("intent") or "general_research"),
            },
            "depth": query_plan.get("depth"),
            "platform_scope": query_plan.get("platform_scope"),
            "collection_modes": query_plan.get("collection_modes") or {},
            "source_count": len(sources),
            "sources": sources,
            "dry_run": dry_run,
            "limits": {
                "max_results_per_source": query_plan.get("max_results_per_source"),
                **execution_options,
            },
        },
        "domain_agent_contract": {
            "role": "Evidence and verification layer for downstream domain agents.",
            "downstream_domains": [
                "insurance_claims",
                "medical_billing_coding",
                "legal_discovery_contract",
                "financial_compliance",
                "procurement_supply_chain",
                "sales_operations",
                "customer_support_qa",
                "code_migration_testing",
            ],
            "non_goals": [
                (
                    "No account mutation, payment, claim submission, legal filing, "
                    "trade placement, or production deployment."
                ),
                (
                    "No bypassing login walls, paywalls, robots controls, platform limits, "
                    "or broker/vendor entitlements."
                ),
                (
                    "No storage of cookies, tokens, protected health information, "
                    "privileged legal data, or customer secrets in artifacts."
                ),
            ],
        },
        "execute_steps": [
            {
                "id": "plan",
                "description": "Select a research pack, build platform queries, and choose connectors.",
                "record": "query_plan.json",
            },
            {
                "id": "collect",
                "description": "Run connector requests with bounded concurrency and retry telemetry.",
                "record": "collection_execution.json",
            },
            {
                "id": "normalize",
                "description": "Normalize connector outputs into evidence rows with stable evidence IDs.",
                "record": "evidence.jsonl",
            },
            {
                "id": "check",
                "description": "Score source quality, detect duplicates, and flag directional conflicts.",
                "record": "evidence_quality.json",
            },
            {
                "id": "review",
                "description": "Ground claims and decision framing in collected evidence.",
                "record": "claim_review.json",
            },
            {
                "id": "stop",
                "description": "Stop for a deterministic reason and write loop status plus feedback.",
                "record": "loop_record.json",
            },
        ],
        "checks": [
            {
                "id": "context_hygiene",
                "kind": "context",
                "pass_condition": (
                    "Raw evidence is offloaded to artifacts and sensitive fields are absent."
                ),
            },
            {
                "id": "stop_brakes",
                "kind": "brake",
                "pass_condition": (
                    "Worker, retry, timeout, and per-source result limits are explicit."
                ),
            },
            {
                "id": "critic_separation",
                "kind": "critic",
                "pass_condition": (
                    "Quality, claim, and decision checks are recorded separately from collection."
                ),
            },
            {
                "id": "tool_focus",
                "kind": "tooling",
                "pass_condition": (
                    "Connector plans are small, explicit, non-overlapping, and read-oriented."
                ),
            },
            {
                "id": "bounded_execution",
                "kind": "brake",
                "pass_condition": "Connector retries, worker count, and optional timeout are explicit.",
            },
            {
                "id": "executable_sources",
                "kind": "input",
                "pass_condition": "At least one connector request is planned, unless this is a dry run.",
            },
            {
                "id": "evidence_collected",
                "kind": "completion",
                "pass_condition": "At least one normalized evidence row is collected for executed runs.",
            },
            {
                "id": "source_quality",
                "kind": "critic",
                "pass_condition": f"Average evidence quality is >= {QUALITY_PASS_THRESHOLD}.",
            },
            {
                "id": "duplicate_pressure",
                "kind": "critic",
                "pass_condition": "Duplicate clusters are absent or explicitly recorded for review.",
            },
            {
                "id": "conflict_review",
                "kind": "critic",
                "pass_condition": "Directional conflicts are absent or explicitly recorded for review.",
            },
            {
                "id": "claim_grounding",
                "kind": "critic",
                "pass_condition": "Claim review is not based on zero evidence for executed runs.",
            },
            {
                "id": "target_claim_threshold",
                "kind": "critic",
                "pass_condition": (
                    "Structured targets expose baseline_only unless a current final official JD passes."
                ),
            },
            {
                "id": "connector_health",
                "kind": "tooling",
                "pass_condition": "Connector warnings are absent or translated into feedback actions.",
            },
        ],
        "feedback_rules": [
            {
                "when": "failed_no_sources",
                "action": (
                    "Add pack sources, external evidence, AgentReach/OpenCLI bridges, "
                    "or a public connector."
                ),
            },
            {
                "when": "failed_no_rows",
                "action": (
                    "Broaden platform scope, simplify the query, install optional connectors, "
                    "or import authorized JSONL evidence."
                ),
            },
            {
                "when": "low_source_quality",
                "action": (
                    "Prefer primary/official sources, add source confidence metadata, "
                    "or collect corroborating evidence."
                ),
            },
            {
                "when": "directional_conflict",
                "action": "Pause final synthesis and reconcile the opposing evidence chains.",
            },
            {
                "when": "connector_warning",
                "action": "Run research-engine doctor and repair missing/auth-expired upstream tools.",
            },
            {
                "when": "context_hygiene_failure",
                "action": (
                    "Remove sensitive fields, import only sanitized external evidence, "
                    "and keep raw captures in local authorized stores."
                ),
            },
            {
                "when": "tool_sprawl",
                "action": (
                    "Split the request into focused passes or narrow platform scope "
                    "before collecting more sources."
                ),
            },
            {
                "when": "critic_missing",
                "action": (
                    "Write quality, claim, and decision artifacts before downstream LLM "
                    "or domain-agent use."
                ),
            },
            {
                "when": "unbounded_timeout",
                "action": "Set --source-timeout-seconds for long-running or fragile connectors.",
            },
        ],
        "records": [
            "run_manifest.json",
            "query_plan.json",
            "collection_execution.json",
            "evidence.jsonl",
            "evidence_quality.json",
            "claim_review.json",
            "supply_demand_matrix.json",
            "decision_brief.json",
            "loop_contract.json",
            "loop_record.json",
            "research_report.md",
        ],
        "stop_conditions": {
            "success": [
                "Executed runs collect evidence and pass critical checks.",
                "Dry runs produce a complete plan and stop before collection.",
            ],
            "stop_and_report": [
                "No executable sources are available.",
                "Sources run but return no rows.",
                "Critical source quality or claim grounding checks fail.",
                "Human judgment is required for low-confidence or conflicting evidence.",
            ],
        },
        "human_gates": [
            "Installing or authenticating optional upstream tools.",
            "Using paid, private, or login-protected sources.",
            "Publishing, trading, messaging, or account-mutating actions based on research.",
            "Accepting low-confidence conclusions as decision-ready.",
        ],
        "acceptance": [
            "Artifacts are written before LLM analysis.",
            "The loop stop reason is explicit.",
            "Failures map to next actions instead of silent retries.",
            "A separate critic/check layer can say no to a fluent but unsupported answer.",
            (
                "Domain agents consume evidence artifacts and loop status, while high-risk "
                "actions remain behind human gates."
            ),
        ],
    }


def build_loop_record(
    *,
    topic: str,
    status: str,
    dry_run: bool,
    rows: list[dict[str, Any]],
    warnings: list[str],
    query_plan: dict[str, Any],
    execution_report: dict[str, Any],
    quality_report: dict[str, Any],
    claim_review: dict[str, Any],
    decision_brief: dict[str, Any],
) -> dict[str, Any]:
    """Build the concrete check/feedback record for a completed run."""

    check_results = [
        check_context_hygiene(rows=rows, dry_run=dry_run),
        check_stop_brakes(query_plan=query_plan, execution_report=execution_report),
        check_critic_separation(
            quality_report=quality_report,
            claim_review=claim_review,
            decision_brief=decision_brief,
            dry_run=dry_run,
        ),
        check_tool_focus(query_plan=query_plan),
        check_bounded_execution(execution_report),
        check_executable_sources(query_plan=query_plan, dry_run=dry_run),
        check_evidence_collected(rows=rows, dry_run=dry_run),
        check_source_quality(rows=rows, quality_report=quality_report, dry_run=dry_run),
        check_duplicate_pressure(quality_report=quality_report),
        check_conflict_review(quality_report=quality_report),
        check_claim_grounding(claim_review=claim_review, dry_run=dry_run),
        check_target_claim_threshold(claim_review=claim_review, dry_run=dry_run),
        check_connector_health(warnings=warnings),
    ]
    feedback_actions = build_feedback_actions(
        status=status,
        check_results=check_results,
        warnings=warnings,
    )
    loop_status = summarize_loop_status(status=status, check_results=check_results)
    return {
        "generated_at": utc_now(),
        "loop_id": "research_loop_v1",
        "topic": topic,
        "run_status": status,
        "loop_status": loop_status,
        "stop_reason": stop_reason(status=status, dry_run=dry_run, check_results=check_results),
        "check_results": check_results,
        "feedback_actions": feedback_actions,
        "records_written": {
            "query_plan": "query_plan.json",
            "execution": "collection_execution.json",
            "evidence": "evidence.jsonl",
            "quality": "evidence_quality.json",
            "claims": "claim_review.json",
            "decision": "decision_brief.json",
        },
        "critic_summary": {
            "stance": (claim_review.get("overall") or {}).get("stance"),
            "confidence": (claim_review.get("overall") or {}).get("confidence"),
            "support_level": (claim_review.get("overall") or {}).get("support_level"),
            "action_bias": decision_brief.get("action_bias"),
            "average_quality_score": quality_report.get("average_quality_score"),
            "conflict_flag_count": len(quality_report.get("conflict_flags") or []),
        },
    }


def check_context_hygiene(*, rows: list[dict[str, Any]], dry_run: bool) -> dict[str, Any]:
    if dry_run:
        return skipped("context_hygiene", "Dry run wrote plan artifacts without raw evidence rows.")
    sensitive_paths = sensitive_artifact_paths(rows)
    if sensitive_paths:
        preview = ", ".join(sensitive_paths[:5])
        return fail(
            "context_hygiene",
            f"Potential sensitive artifact field(s): {preview}.",
            "Remove secrets/session fields and import only sanitized evidence artifacts.",
        )
    if len(rows) > REPORT_EVIDENCE_PREVIEW_LIMIT:
        return passed(
            "context_hygiene",
            (
                f"{len(rows)} evidence row(s) are offloaded to evidence.jsonl; "
                f"report previews are capped at {REPORT_EVIDENCE_PREVIEW_LIMIT} rows."
            ),
        )
    return passed(
        "context_hygiene",
        "Evidence is represented as artifact rows, not inline run context.",
    )


def check_stop_brakes(
    *,
    query_plan: dict[str, Any],
    execution_report: dict[str, Any],
) -> dict[str, Any]:
    max_results = int(query_plan.get("max_results_per_source") or 0)
    max_workers = int(execution_report.get("max_workers") or 0)
    retries = int(execution_report.get("retries") or 0)
    timeout = execution_report.get("source_timeout_seconds")
    if max_results <= 0:
        return fail(
            "stop_brakes",
            "No positive per-source result limit is configured.",
            "Set a positive max_results_per_source before collection.",
        )
    if max_workers <= 0 or retries < 0:
        return fail(
            "stop_brakes",
            "Invalid worker or retry brake.",
            "Set positive max workers and non-negative retries.",
        )
    if timeout is None:
        return warn(
            "stop_brakes",
            "No source timeout configured.",
            "Set --source-timeout-seconds so long-running connectors have a hard stop.",
        )
    return passed(
        "stop_brakes",
        (
            f"Limits set: max_results={max_results}, max_workers={max_workers}, "
            f"retries={retries}, timeout={timeout}."
        ),
    )


def check_critic_separation(
    *,
    quality_report: dict[str, Any],
    claim_review: dict[str, Any],
    decision_brief: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any]:
    if dry_run:
        return skipped("critic_separation", "Dry run stopped before critic artifacts.")
    missing: list[str] = []
    if "average_quality_score" not in quality_report:
        missing.append("evidence_quality.average_quality_score")
    if "duplicate_cluster_count" not in quality_report:
        missing.append("evidence_quality.duplicate_cluster_count")
    if "conflict_flags" not in quality_report:
        missing.append("evidence_quality.conflict_flags")
    if not (claim_review.get("overall") or {}).get("stance"):
        missing.append("claim_review.overall.stance")
    if "action_bias" not in decision_brief:
        missing.append("decision_brief.action_bias")
    if missing:
        return fail(
            "critic_separation",
            "Missing critic artifact field(s): " + ", ".join(missing) + ".",
            "Write quality, claim, and decision artifacts before downstream agent use.",
        )
    return passed("critic_separation", "Quality, claim, and decision critic artifacts are present.")


def check_tool_focus(*, query_plan: dict[str, Any]) -> dict[str, Any]:
    sources = [source for source in query_plan.get("sources") or [] if isinstance(source, dict)]
    if not sources:
        return skipped("tool_focus", "No connector plan to focus-check.")
    missing_connectors = [
        str(source.get("source_id") or "<unknown>")
        for source in sources
        if not source.get("connector")
    ]
    if missing_connectors:
        return fail(
            "tool_focus",
            "Source(s) without connector: " + ", ".join(missing_connectors) + ".",
            "Assign an explicit read-oriented connector to every planned source.",
        )
    source_ids = [str(source.get("source_id") or "") for source in sources]
    duplicate_source_ids = sorted(
        {source_id for source_id in source_ids if source_ids.count(source_id) > 1}
    )
    connector_ids = sorted(
        {str(source.get("connector")) for source in sources if source.get("connector")}
    )
    if duplicate_source_ids:
        return warn(
            "tool_focus",
            "Duplicate source id(s): " + ", ".join(duplicate_source_ids) + ".",
            "Give each source a stable unique source_id before treating corroboration as independent.",
        )
    if len(connector_ids) > FOCUSED_CONNECTOR_LIMIT or len(sources) > FOCUSED_SOURCE_LIMIT:
        return warn(
            "tool_focus",
            f"{len(sources)} source(s) across {len(connector_ids)} connector type(s).",
            "Split into focused passes or narrow platform scope before collection.",
        )
    return passed(
        "tool_focus",
        (
            f"{len(sources)} source(s) across {len(connector_ids)} connector type(s): "
            f"{', '.join(connector_ids)}."
        ),
    )


def check_bounded_execution(execution_report: dict[str, Any]) -> dict[str, Any]:
    max_workers = int(execution_report.get("max_workers") or 0)
    retries = int(execution_report.get("retries") or 0)
    timeout = execution_report.get("source_timeout_seconds")
    if max_workers <= 0 or retries < 0:
        return fail(
            "bounded_execution",
            "Invalid execution bounds.",
            "Set positive max workers and non-negative retries.",
        )
    if timeout is None:
        return warn(
            "bounded_execution",
            "No source timeout configured.",
            "Set --source-timeout-seconds for fragile or long-running connectors.",
        )
    return passed("bounded_execution", "Execution has worker, retry, and timeout bounds.")


def check_executable_sources(*, query_plan: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    source_count = len(query_plan.get("sources") or [])
    if dry_run:
        return skipped("executable_sources", f"Dry run planned {source_count} source(s).")
    if source_count > 0:
        return passed("executable_sources", f"{source_count} executable source(s) planned.")
    return fail(
        "executable_sources",
        "No executable sources planned.",
        "Add sources or import external evidence.",
    )


def check_evidence_collected(*, rows: list[dict[str, Any]], dry_run: bool) -> dict[str, Any]:
    if dry_run:
        return skipped("evidence_collected", "Dry run stopped before collection.")
    if rows:
        return passed("evidence_collected", f"{len(rows)} evidence row(s) collected.")
    return fail(
        "evidence_collected",
        "No evidence rows collected.",
        "Broaden collection or repair connectors.",
    )


def check_source_quality(
    *,
    rows: list[dict[str, Any]],
    quality_report: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any]:
    if dry_run:
        return skipped("source_quality", "Dry run stopped before quality scoring.")
    if not rows:
        return fail(
            "source_quality",
            "No evidence rows to score.",
            "Collect evidence before synthesis.",
        )
    average = float(quality_report.get("average_quality_score") or 0.0)
    if average >= QUALITY_PASS_THRESHOLD:
        return passed("source_quality", f"Average quality score is {average}.")
    return warn(
        "source_quality",
        f"Average quality score is {average}.",
        "Collect primary or higher-confidence sources before trusting synthesis.",
    )


def check_duplicate_pressure(*, quality_report: dict[str, Any]) -> dict[str, Any]:
    duplicate_count = int(quality_report.get("duplicate_cluster_count") or 0)
    if duplicate_count == 0:
        return passed("duplicate_pressure", "No duplicate clusters detected.")
    return warn(
        "duplicate_pressure",
        f"{duplicate_count} duplicate cluster(s) detected.",
        "Review duplicate clusters before counting corroboration.",
    )


def check_conflict_review(*, quality_report: dict[str, Any]) -> dict[str, Any]:
    conflict_count = len(quality_report.get("conflict_flags") or [])
    if conflict_count == 0:
        return passed("conflict_review", "No directional conflict flags detected.")
    return warn(
        "conflict_review",
        f"{conflict_count} directional conflict flag(s) detected.",
        "Reconcile opposing evidence chains before final synthesis.",
    )


def check_claim_grounding(*, claim_review: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    if dry_run:
        return skipped("claim_grounding", "Dry run stopped before claim grounding.")
    stance = str((claim_review.get("overall") or {}).get("stance") or "")
    if stance == "evidence_collected_needs_analysis":
        return warn(
            "claim_grounding",
            "Evidence was collected, but no pack-specific claim buckets were proven.",
            "Add claim specs or run a human/LLM analysis pass before treating this as decision-ready.",
        )
    if stance and stance != "no_evidence_collected":
        return passed("claim_grounding", f"Claim review stance is {stance}.")
    return fail(
        "claim_grounding",
        "Claim review has no collected evidence.",
        "Do not pass this run to final LLM analysis.",
    )


def check_target_claim_threshold(
    *, claim_review: dict[str, Any], dry_run: bool
) -> dict[str, Any]:
    if claim_review.get("schema_version") != "target_claim_review.v1":
        return skipped("target_claim_threshold", "Run does not use the structured target contract.")
    if dry_run:
        return skipped("target_claim_threshold", "Dry run stopped before target claim gates.")
    support_level = str((claim_review.get("overall") or {}).get("support_level") or "")
    if support_level and support_level != "baseline_only":
        return passed("target_claim_threshold", f"Target support level is {support_level}.")
    return warn(
        "target_claim_threshold",
        "No current final official JD passed the complete target tuple gates.",
        "Keep downstream coaching at baseline_only and retry official discovery later.",
    )


def check_connector_health(*, warnings: list[str]) -> dict[str, Any]:
    if not warnings:
        return passed("connector_health", "No connector warnings recorded.")
    return warn(
        "connector_health",
        f"{len(warnings)} warning(s) recorded.",
        "Run research-engine doctor and repair optional connector setup if coverage matters.",
    )


def build_feedback_actions(
    *,
    status: str,
    check_results: list[dict[str, Any]],
    warnings: list[str],
) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    if status == "failed_no_sources":
        actions.append(
            {
                "reason": "failed_no_sources",
                "action": "Add pack sources, pass --external-evidence, or enable AgentReach/OpenCLI bridge sources.",
            }
        )
    if status == "failed_no_rows":
        actions.append(
            {
                "reason": "failed_no_rows",
                "action": "Broaden --platform-scope, simplify the query, or repair missing/auth-expired connectors.",
            }
        )
    for result in check_results:
        result_status = result.get("status")
        if result_status not in {"warn", "fail"}:
            continue
        action = str(result.get("feedback_action") or "")
        if action:
            actions.append({"reason": str(result.get("check_id") or "check"), "action": action})
    if warnings and not any(action["reason"] == "connector_health" for action in actions):
        actions.append(
            {
                "reason": "connector_warning",
                "action": "Inspect connector warnings before relying on source coverage.",
            }
        )
    return dedupe_actions(actions)


def dedupe_actions(actions: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, str]] = []
    for action in actions:
        key = (action["reason"], action["action"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(action)
    return unique


def summarize_loop_status(*, status: str, check_results: list[dict[str, Any]]) -> str:
    if status == "planned":
        return "planned"
    if any(result.get("status") == "fail" for result in check_results):
        return "blocked"
    if any(result.get("status") == "warn" for result in check_results):
        return "complete_with_review_required"
    return "complete"


def stop_reason(*, status: str, dry_run: bool, check_results: list[dict[str, Any]]) -> str:
    if dry_run or status == "planned":
        return "planned_before_collection"
    if status == "failed_no_sources":
        return "no_executable_sources"
    if status == "failed_no_rows":
        return "sources_returned_no_evidence"
    failed = [result for result in check_results if result.get("status") == "fail"]
    if failed:
        return f"critical_check_failed:{failed[0].get('check_id')}"
    warned = [result for result in check_results if result.get("status") == "warn"]
    if warned:
        if any(result.get("check_id") == "target_claim_threshold" for result in warned):
            return "target_evidence_threshold_not_met"
        return "completed_with_review_required"
    return "acceptance_checks_passed"


def passed(check_id: str, observed: str) -> dict[str, Any]:
    return {"check_id": check_id, "status": "pass", "observed": observed}


def warn(check_id: str, observed: str, feedback_action: str) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "status": "warn",
        "observed": observed,
        "feedback_action": feedback_action,
    }


def fail(check_id: str, observed: str, feedback_action: str) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "status": "fail",
        "observed": observed,
        "feedback_action": feedback_action,
    }


def skipped(check_id: str, observed: str) -> dict[str, Any]:
    return {"check_id": check_id, "status": "skip", "observed": observed}


def sensitive_artifact_paths(rows: list[dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    for index, row in enumerate(rows):
        prefix = f"rows[{index}]"
        row_paths = {*sensitive_paths(row), *sensitive_value_paths(row)}
        paths.extend(f"{prefix}.{path}" for path in sorted(row_paths))
    return paths
