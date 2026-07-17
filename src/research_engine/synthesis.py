"""Deterministic synthesis over collected evidence."""

from __future__ import annotations

from collections import Counter
from typing import Any

from research_engine.conflicts import build_claim_chains
from research_engine.models import utc_now
from research_engine.quality import is_claim_eligible


def build_claim_review(
    *,
    topic: str,
    pack: dict[str, Any],
    rows: list[dict[str, Any]],
    warnings: list[str],
    conflict_flags: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    specs = [spec for spec in pack.get("claim_specs") or [] if isinstance(spec, dict)]
    if not specs:
        return build_generic_claim_review(topic=topic, rows=rows, warnings=warnings)
    polarized_rows = assign_claim_polarities(rows, specs=specs)
    documents = build_documents(polarized_rows)
    claims = [score_claim(spec, documents) for spec in specs]
    for claim, spec in zip(claims, specs):
        chain = build_claim_chains(
            polarized_rows,
            claim_id=str(claim.get("claim_id") or "claim"),
            min_support=max(1, int(spec.get("min_independent_support") or 2)),
        )
        claim["evidence_chains"] = chain
        claim["confidence_ceiling"] = chain["confidence_ceiling"]
        if chain["stance"] == "conflicted":
            claim["verdict"] = "conflicted"
        elif chain["stance"] == "opposed":
            claim["verdict"] = "opposed"
        elif chain["stance"] == "needs_more_evidence" and claim["evidence_count"]:
            claim["verdict"] = "needs_more_evidence"
    if rows and not documents:
        for claim in claims:
            claim["verdict"] = "insufficient_valid_evidence"
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
    confidence = "medium" if documents else "low"
    if supported >= int(rules.get("supported_claims_for_high_confidence") or supported_threshold):
        confidence = "high"
    elif supported == 0:
        confidence = "low"
    cited_ids = {
        str(evidence_id)
        for claim in claims
        for evidence_id in claim.get("evidence_ids") or []
        if evidence_id
    }
    applicable_conflicts = [
        flag
        for flag in conflict_flags or []
        if conflict_overlaps_claims(flag, cited_ids)
    ]
    if applicable_conflicts:
        if stance in {"supported", "partially_supported"}:
            stance = "conflicted"
        if confidence == "high":
            confidence = "medium"
    chain_conflict = any(
        (claim.get("evidence_chains") or {}).get("stance") == "conflicted"
        for claim in claims
    )
    if chain_conflict:
        stance = "conflicted"
        if confidence == "high":
            confidence = "medium"
    conflict_flag_ids = [str(flag.get("flag_id") or "") for flag in applicable_conflicts]
    conflict_evidence_ids = sorted(
        cited_ids
        & {
            str(evidence_id)
            for flag in applicable_conflicts
            for evidence_id in [
                *(flag.get("support_evidence_ids") or []),
                *(flag.get("oppose_evidence_ids") or []),
            ]
            if evidence_id
        }
    )
    return {
        "generated_at": utc_now(),
        "topic": topic,
        "profile": str(pack.get("profile") or pack.get("id") or "generic"),
        "overall": {
            "stance": stance,
            "confidence": confidence,
            "summary": summarize_stance(pack, stance, supported, partial),
            "risk_flags": list(warnings),
            "conflict_flag_ids": conflict_flag_ids,
            "conflict_evidence_ids": conflict_evidence_ids,
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
    not_investment_advice = bool(
        rules.get("not_investment_advice") or pack.get("intent") == "financial_market_research"
    )
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
        "not_investment_advice": not_investment_advice,
        "not_professional_advice": True,
    }


def build_generic_claim_review(
    *,
    topic: str,
    rows: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    eligible_rows = [row for row in rows if is_claim_eligible(row)]
    connectors = Counter(str(row.get("connector") or "unknown") for row in eligible_rows)
    chain = build_claim_chains(eligible_rows, claim_id="topic-main", min_support=2)
    has_conflict = chain["stance"] == "conflicted"
    return {
        "generated_at": utc_now(),
        "topic": topic,
        "profile": "generic",
        "overall": {
            "stance": (
                "conflicted"
                if has_conflict
                else (
                    "evidence_collected_needs_analysis"
                    if eligible_rows
                    else "no_evidence_collected"
                )
            ),
            "confidence": "medium" if eligible_rows else "low",
            "summary": (
                f"Collected {len(eligible_rows)} eligible row(s) from {len(rows)} total "
                f"across {len(connectors)} connector(s)."
            ),
            "risk_flags": list(warnings),
        },
        "claims": [
            {
                "claim_id": "topic-main",
                "question": topic,
                "verdict": (
                    "evidence_collected_needs_analysis"
                    if eligible_rows
                    else "no_evidence_collected"
                ),
                "evidence_ids": [str(row.get("evidence_id") or "") for row in eligible_rows],
                "source_mix": dict(connectors),
                "evidence_chains": chain,
            }
        ],
        "connector_warnings": warnings,
    }


def assign_claim_polarities(
    rows: list[dict[str, Any]], *, specs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Derive conservative row-level claim polarity while respecting explicit labels."""

    polarized: list[dict[str, Any]] = []
    for original in rows:
        row = dict(original)
        mapping = dict(row.get("claim_polarities") or {})
        text = " ".join(
            str(row.get(key) or "") for key in ("title", "text", "text_excerpt")
        ).lower()
        for spec in specs:
            claim_id = str(spec.get("claim_id") or "claim")
            if claim_id in mapping or row.get("claim_polarity") or row.get("polarity"):
                continue
            support = [str(value).lower() for value in spec.get("keywords") or []]
            oppose = [str(value).lower() for value in spec.get("oppose_keywords") or []]
            support_hit = any(value and value in text for value in support)
            oppose_hit = any(value and value in text for value in oppose)
            if support_hit != oppose_hit:
                mapping[claim_id] = "support" if support_hit else "oppose"
        if mapping:
            row["claim_polarities"] = mapping
        polarized.append(row)
    return polarized


def build_documents(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        if not is_claim_eligible(row):
            continue
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


def conflict_overlaps_claims(flag: dict[str, Any], cited_ids: set[str]) -> bool:
    support_ids = {str(value) for value in flag.get("support_evidence_ids") or [] if value}
    oppose_ids = {str(value) for value in flag.get("oppose_evidence_ids") or [] if value}
    if not cited_ids.intersection(support_ids | oppose_ids):
        return False
    return any(support_id != oppose_id for support_id in support_ids for oppose_id in oppose_ids)


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
