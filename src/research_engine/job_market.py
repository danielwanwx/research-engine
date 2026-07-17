"""Scoped point-in-time job-market aggregation."""

from __future__ import annotations

from datetime import date
from collections import Counter
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from research_engine.planning import validate_research_scope
from research_engine.quality import is_claim_eligible, is_evidence_eligible
from research_engine.targets import match_geography


SCOPE_SCHEMA = "research_scope.v1"
SNAPSHOT_SCHEMA = "job_market_snapshot.v1"


def normalize_job_scope(scope: dict[str, Any] | None) -> dict[str, Any]:
    """Validate and normalize the explicit scope required for quantitative counts."""

    if not isinstance(scope, dict) or scope.get("schema_version") != SCOPE_SCHEMA:
        raise ValueError("job-market snapshots require explicit research_scope.v1")
    if scope.get("profile") != "job_market":
        raise ValueError("research scope profile must be job_market")
    try:
        resolved = validate_research_scope(scope)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    try:
        as_of = date.fromisoformat(str(resolved.get("as_of") or ""))
    except ValueError as exc:
        raise ValueError("job-market scope requires ISO as_of date") from exc
    return {**resolved, "as_of": as_of.isoformat()}


def build_job_market_snapshot(
    rows: list[dict[str, Any]],
    *,
    scope: dict[str, Any],
    requested_sources: list[str] | None = None,
    checked_sources: list[str] | None = None,
    failed_sources: list[str] | None = None,
    unsupported_sources: list[str] | None = None,
) -> dict[str, Any]:
    """Aggregate rows into mutually exclusive point-in-time outcome counts."""

    resolved_scope = normalize_job_scope(scope)
    requested = _unique(
        requested_sources or resolved_scope["filters"].get("companies", [])
    )
    checked = _unique(checked_sources or [])
    failed = _unique(failed_sources or [])
    unsupported = _unique(unsupported_sources or [])
    counts = {
        "observed": len(rows),
        "active": 0,
        "closed": 0,
        "duplicate": 0,
        "rejected": 0,
        "unknown_status": 0,
    }
    openings: list[dict[str, Any]] = []
    opening_by_key: dict[str, dict[str, Any]] = {}
    rejection_reasons: Counter[str] = Counter()

    for row in rows:
        status = str(row.get("current_status") or "unknown").lower()
        if status == "closed":
            counts["closed"] += 1
            continue
        if status in {"", "unknown"}:
            counts["unknown_status"] += 1
            continue
        if status != "active":
            counts["rejected"] += 1
            continue
        reasons = _active_rejection_reasons(row, resolved_scope)
        if reasons:
            counts["rejected"] += 1
            rejection_reasons.update(reasons)
            continue

        identity = _job_identity(row)
        if identity in opening_by_key:
            counts["duplicate"] += 1
            if identity in opening_by_key:
                evidence_id = str(row.get("evidence_id") or "")
                if evidence_id:
                    opening_by_key[identity]["evidence_ids"].append(evidence_id)
                compensation = _compensation(row)
                if compensation and not opening_by_key[identity]["compensation"]:
                    opening_by_key[identity]["compensation"] = compensation
                    opening_by_key[identity]["field_evidence_ids"]["compensation"] = [
                        evidence_id
                    ]
            continue

        opening = _opening(row, identity=identity)
        opening_by_key[identity] = opening
        openings.append(opening)
        counts["active"] += 1

    return {
        "schema_version": SNAPSHOT_SCHEMA,
        "as_of": resolved_scope["as_of"],
        "scope": resolved_scope,
        "coverage": {
            "requested": requested,
            "checked": checked,
            "failed": failed,
            "unsupported": unsupported,
            "denominator": len(requested),
            "checked_count": len(checked),
        },
        "counts": counts,
        "rejection_reason_counts": dict(rejection_reasons),
        "openings": openings,
        "trend": None,
        "trend_status": "unavailable_without_comparable_prior_snapshot",
    }


def _active_eligible(row: dict[str, Any], scope: dict[str, Any]) -> bool:
    return not _active_rejection_reasons(row, scope)


def _active_rejection_reasons(
    row: dict[str, Any], scope: dict[str, Any]
) -> list[str]:
    reasons: list[str] = []
    fitness = row.get("claim_fitness")
    official = (
        str(row.get("source_class") or "").lower() == "official_jd"
        or str(row.get("source_kind") or "").lower() == "official_job_posting"
    )
    current_official = (
        official
        and str(row.get("current_status") or "").lower() == "active"
        and row.get("is_final_page") is True
        and is_evidence_eligible(row)
    )
    fitness_reasons = (
        {str(reason) for reason in fitness.get("rejection_reasons") or []}
        if isinstance(fitness, dict)
        else set()
    )
    if isinstance(fitness, dict) and fitness.get("disposition") != "accepted" and not (
        current_official and fitness_reasons == {"duplicate"}
    ):
        reasons.append("claim_fitness_rejected")
    if not official:
        reasons.append("not_official_job_posting")
    if row.get("is_final_page") is not True:
        reasons.append("not_final_page")
    if not current_official and (
        row.get("claim_eligible") is False or not is_claim_eligible(row)
    ):
        reasons.append("claim_ineligible")
    if not current_official and str(row.get("freshness_status") or "").lower() == "stale":
        reasons.append("stale")
    match = row.get("target_match")
    if isinstance(match, dict) and any(
        match.get(key) == "mismatch"
        for key in ("company", "role_title", "role_family", "geography")
    ):
        reasons.append("target_mismatch")

    filters = scope["filters"]
    company = str(row.get("company") or "").lower()
    if filters.get("companies") and company not in {
        value.lower() for value in filters["companies"]
    }:
        reasons.append("company_mismatch")
    title = str(row.get("title") or "").lower()
    if filters.get("role_terms") and not any(
        value.lower() in title for value in filters["role_terms"]
    ):
        reasons.append("role_mismatch")
    level_text = f"{row.get('level') or ''} {row.get('title') or ''}".lower()
    if filters.get("levels") and not any(
        value.lower() in level_text for value in filters["levels"]
    ):
        reasons.append("level_mismatch")
    geography = str(row.get("geography") or row.get("location") or "")
    if filters.get("geography") and not any(
        value.lower() == geography.lower()
        or match_geography(value, geography) in {"exact", "compatible"}
        for value in filters["geography"]
    ):
        reasons.append("geography_mismatch")
    return list(dict.fromkeys(reasons))


def _job_identity(row: dict[str, Any]) -> str:
    requisition = str(row.get("requisition_id") or row.get("job_id") or "").strip().lower()
    if requisition:
        return f"req:{requisition}"
    url = str(row.get("canonical_url") or row.get("final_url") or row.get("url") or "")
    canonical = _canonical_job_url(url)
    if canonical:
        return f"url:{canonical}"
    return "row:" + "|".join(
        str(row.get(key) or "").strip().lower()
        for key in ("company", "title", "geography")
    )


def _opening(row: dict[str, Any], *, identity: str) -> dict[str, Any]:
    evidence_id = str(row.get("evidence_id") or "")
    opening = {
        "job_identity": identity,
        "company": str(row.get("company") or ""),
        "title": str(row.get("title") or ""),
        "role_family": str(row.get("role_family") or ""),
        "level": str(row.get("level") or ""),
        "geography": str(row.get("geography") or row.get("location") or ""),
        "skills": _list(row.get("skills")),
        "compensation": _compensation(row),
        "canonical_url": _canonical_job_url(
            str(row.get("canonical_url") or row.get("final_url") or row.get("url") or "")
        ),
        "evidence_ids": [evidence_id] if evidence_id else [],
    }
    opening["field_evidence_ids"] = {
        field: [evidence_id]
        for field in (
            "company",
            "title",
            "role_family",
            "level",
            "geography",
            "skills",
            "compensation",
        )
        if evidence_id and opening[field]
    }
    return opening


def _canonical_job_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))


def _compensation(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("compensation")
    if isinstance(value, dict):
        return dict(value)
    fields = {
        target: row.get(source)
        for target, source in (
            ("currency", "salary_currency"),
            ("min", "salary_min"),
            ("max", "salary_max"),
            ("period", "salary_period"),
        )
        if row.get(source) is not None
    }
    return fields


def _list(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    return [str(item).strip() for item in values if str(item or "").strip()]


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))
