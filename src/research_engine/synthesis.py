"""Deterministic synthesis over collected evidence."""

from __future__ import annotations

from collections import Counter
from typing import Any

from research_engine.models import utc_now


def build_claim_review(
    *,
    topic: str,
    pack: dict[str, Any],
    rows: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    specs = [spec for spec in pack.get("claim_specs") or [] if isinstance(spec, dict)]
    if not specs:
        return build_generic_claim_review(topic=topic, rows=rows, warnings=warnings)
    documents = build_documents(rows)
    claims = [score_claim(spec, documents) for spec in specs]
    supported = sum(1 for claim in claims if claim["verdict"] == "supported")
    partial = sum(1 for claim in claims if claim["verdict"] == "partially_supported")
    rules = pack.get("decision_rules") or {}
    supported_threshold = int(rules.get("supported_claims_for_supported") or max(1, len(specs)))
    partial_threshold = int(rules.get("supported_or_partial_for_partial") or supported_threshold)
    stance = "needs_more_evidence"
    if supported >= supported_threshold:
        stance = "supported"
    elif supported + partial >= partial_threshold:
        stance = "partially_supported"
    confidence = "medium" if rows else "low"
    if supported >= int(rules.get("supported_claims_for_high_confidence") or supported_threshold):
        confidence = "high"
    elif supported == 0:
        confidence = "low"
    return {
        "generated_at": utc_now(),
        "topic": topic,
        "profile": str(pack.get("profile") or pack.get("id") or "generic"),
        "overall": {
            "stance": stance,
            "confidence": confidence,
            "summary": summarize_stance(pack, stance, supported, partial),
            "risk_flags": list(warnings),
        },
        "claims": claims,
        "connector_warnings": warnings,
    }


def build_supply_demand_matrix(
    *,
    topic: str,
    pack: dict[str, Any],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    nodes = [node for node in pack.get("matrix_nodes") or [] if isinstance(node, dict)]
    documents = build_documents(rows)
    if not nodes:
        return {
            "generated_at": utc_now(),
            "topic": topic,
            "profile": str(pack.get("profile") or "generic"),
            "summary": {"gap_assessment": "not_applicable", "evidence_rows": len(rows)},
            "rows": [],
            "entities": {},
        }
    matrix_rows = [score_matrix_node(node, documents) for node in nodes]
    supported_by_side = Counter(row["side"] for row in matrix_rows if row["verdict"] == "supported")
    gap_assessment = "needs_more_evidence"
    if supported_by_side.get("demand", 0) and supported_by_side.get("constraint", 0):
        gap_assessment = "demand_outpacing_near_term_supply"
    elif supported_by_side.get("demand", 0):
        gap_assessment = "strong_demand_supply_gap_unconfirmed"
    return {
        "generated_at": utc_now(),
        "topic": topic,
        "profile": str(pack.get("profile") or pack.get("id") or "generic"),
        "summary": {
            "gap_assessment": gap_assessment,
            "supported_nodes_by_side": dict(supported_by_side),
            "evidence_rows": len(rows),
        },
        "rows": matrix_rows,
        "entities": extract_entities(documents, pack),
    }


def build_decision_brief(
    *,
    topic: str,
    pack: dict[str, Any],
    claim_review: dict[str, Any],
    matrix: dict[str, Any],
) -> dict[str, Any]:
    overall = claim_review.get("overall") or {}
    rules = pack.get("decision_rules") or {}
    stance = str(overall.get("stance") or "unknown")
    action_bias = (rules.get("action_bias_by_stance") or {}).get(stance) or "analyze_before_action"
    return {
        "generated_at": utc_now(),
        "topic": topic,
        "profile": str(claim_review.get("profile") or "generic"),
        "decision_type": str(pack.get("intent") or "research_summary"),
        "headline": str(overall.get("summary") or "Evidence collected; analysis required."),
        "stance": stance,
        "confidence": str(overall.get("confidence") or "medium"),
        "action_bias": str(action_bias),
        "rationale": [
            f"{len([claim for claim in claim_review.get('claims') or [] if claim.get('verdict') == 'supported'])} claim buckets are supported.",
            f"Matrix gap assessment: {(matrix.get('summary') or {}).get('gap_assessment') or 'unknown'}.",
        ],
        "not_investment_advice": True,
    }


def build_generic_claim_review(
    *,
    topic: str,
    rows: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    connectors = Counter(str(row.get("connector") or "unknown") for row in rows)
    return {
        "generated_at": utc_now(),
        "topic": topic,
        "profile": "generic",
        "overall": {
            "stance": "evidence_collected_needs_analysis" if rows else "no_evidence_collected",
            "confidence": "medium" if rows else "low",
            "summary": f"Collected {len(rows)} rows across {len(connectors)} connector(s).",
            "risk_flags": list(warnings),
        },
        "claims": [
            {
                "claim_id": "topic-main",
                "question": topic,
                "verdict": "evidence_collected_needs_analysis" if rows else "no_evidence_collected",
                "evidence_ids": [str(row.get("evidence_id") or "") for row in rows],
                "source_mix": dict(connectors),
            }
        ],
        "connector_warnings": warnings,
    }


def build_documents(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        text = " ".join(
            str(value or "")
            for value in (
                row.get("title"),
                row.get("text"),
                row.get("text_excerpt"),
                row.get("publisher"),
                row.get("connector"),
            )
        ).lower()
        documents.append(
            {
                "evidence_id": str(row.get("evidence_id") or f"ev-{index:04d}"),
                "title": str(row.get("title") or ""),
                "url": str(row.get("url") or row.get("source_url") or ""),
                "connector": str(row.get("connector") or ""),
                "text": text,
                "excerpt": str(row.get("text") or row.get("text_excerpt") or "")[:500],
            }
        )
    return documents


def score_claim(spec: dict[str, Any], documents: list[dict[str, Any]]) -> dict[str, Any]:
    keywords = [str(keyword).lower() for keyword in spec.get("keywords") or []]
    matched = [document for document in documents if any(keyword in document["text"] for keyword in keywords)]
    min_evidence = int(spec.get("min_evidence") or 1)
    verdict = "insufficient_evidence"
    if len(matched) >= min_evidence:
        verdict = "supported"
    elif matched:
        verdict = "partially_supported"
    return {
        "claim_id": str(spec.get("claim_id") or "claim"),
        "question": str(spec.get("question") or ""),
        "verdict": verdict,
        "evidence_count": len(matched),
        "evidence_ids": [document["evidence_id"] for document in matched[:12]],
        "strongest_evidence": matched[:3],
    }


def score_matrix_node(spec: dict[str, Any], documents: list[dict[str, Any]]) -> dict[str, Any]:
    keywords = [str(keyword).lower() for keyword in spec.get("keywords") or []]
    matched = [document for document in documents if any(keyword in document["text"] for keyword in keywords)]
    min_evidence = int(spec.get("min_evidence") or 1)
    verdict = "supported" if len(matched) >= min_evidence else "insufficient_evidence"
    if 0 < len(matched) < min_evidence:
        verdict = "partially_supported"
    return {
        "node_id": str(spec.get("node_id") or "node"),
        "side": str(spec.get("side") or "unknown"),
        "label": str(spec.get("label") or spec.get("node_id") or "node"),
        "verdict": verdict,
        "evidence_count": len(matched),
        "evidence_ids": [document["evidence_id"] for document in matched[:12]],
    }


def extract_entities(documents: list[dict[str, Any]], pack: dict[str, Any]) -> dict[str, list[str]]:
    text = " ".join(document["text"] for document in documents)
    entity_config = pack.get("matrix_entities") or {}
    entities: dict[str, list[str]] = {}
    for side, values in entity_config.items():
        if isinstance(values, dict):
            entities[str(side)] = [str(name) for name, needle in values.items() if str(needle).lower() in text]
    return entities


def summarize_stance(pack: dict[str, Any], stance: str, supported: int, partial: int) -> str:
    templates = (pack.get("decision_rules") or {}).get("stance_summaries") or {}
    template = templates.get(stance) or templates.get("default")
    label = str(pack.get("label") or "Research")
    if template:
        return str(template).format(profile_label=label, supported_count=supported, partial_count=partial)
    if stance == "supported":
        return f"{label} is supported across {supported} claim bucket(s)."
    if stance == "partially_supported":
        return f"{label} is partially supported ({supported} supported, {partial} partial)."
    return f"Evidence is not yet sufficient for a strong {label} conclusion."
