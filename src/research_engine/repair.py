"""Deterministic mapping from failed checks to one bounded repair plan."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


_SIMPLIFY_STOP_WORDS = {
    "adoption",
    "and",
    "file",
    "format",
    "for",
    "open",
    "the",
}
_REPAIR_REASONS = {
    "canonical_refetch_failure",
    "freshness_failure",
    "no_executable_sources",
    "no_relevant_evidence",
    "source_concentration",
}


def progress_fingerprint(
    rows: list[dict[str, Any]],
    failures: list[dict[str, Any]],
) -> str:
    """Fingerprint observable yield and failures without depending on input order."""

    yield_state = sorted(
        (
            str(row.get("canonical_url") or row.get("url") or row.get("evidence_id") or ""),
            str(row.get("freshness_status") or ""),
            str(row.get("content_valid") if "content_valid" in row else ""),
            str(row.get("relevance_score") or ""),
        )
        for row in rows
    )
    failure_state = sorted(
        (str(item.get("facet_id") or ""), str(item.get("reason") or ""))
        for item in failures
    )
    payload = json.dumps(
        {"yield": yield_state, "failures": failure_state},
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_repair_plan(
    facets: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    *,
    as_of: str,
    search_enabled: bool = True,
    pass_number: int = 1,
    previous_progress_fingerprint: str = "",
    current_progress_fingerprint: str = "",
    max_refetch_candidates: int = 5,
) -> dict[str, Any]:
    """Return pass-2 facet mutations or an explicit deterministic stop."""

    if pass_number >= 2:
        return _stopped("repair_limit_reached", current_progress_fingerprint)
    if (
        previous_progress_fingerprint
        and current_progress_fingerprint
        and previous_progress_fingerprint == current_progress_fingerprint
    ):
        return _stopped("repair_no_progress", current_progress_fingerprint)
    if failures and all(
        str(failure.get("reason") or "") == "infrastructure_unavailable"
        for failure in failures
    ):
        return _stopped("infrastructure_unavailable", current_progress_fingerprint)

    by_id = {str(facet.get("facet_id") or ""): facet for facet in facets}
    failures_by_facet: dict[str, list[dict[str, Any]]] = {}
    for failure in failures:
        failures_by_facet.setdefault(str(failure.get("facet_id") or ""), []).append(failure)
    repaired: list[dict[str, Any]] = []
    for facet_id, facet_failures in failures_by_facet.items():
        facet = by_id.get(facet_id)
        valid_failures = [
            (failure, str(failure.get("reason") or ""))
            for failure in facet_failures
            if str(failure.get("reason") or "") in _REPAIR_REASONS
        ]
        if not facet or not facet.get("required") or not valid_failures:
            continue
        candidate = dict(facet)
        original_query = str(candidate.get("query") or "").strip()
        inherited_constraints = [
            str(value).strip()
            for value in candidate.get("repair_constraints") or []
            if str(value).strip()
        ]
        applied_reasons: list[str] = []
        candidate_urls: list[str] = []
        for failure, reason in valid_failures:
            query = str(candidate.get("query") or "").strip()
            if reason == "no_executable_sources":
                if not search_enabled:
                    continue
                source_types = list(candidate.get("source_types") or [])
                candidate["source_types"] = list(dict.fromkeys([*source_types, "web_search"]))
            elif reason == "no_relevant_evidence":
                candidate["query"] = simplify_query(
                    query,
                    required_terms=inherited_constraints,
                )
            elif reason == "freshness_failure":
                candidate["query"] = _append_terms(query, "current", as_of[:4])
            elif reason == "source_concentration":
                candidate["query"] = _append_terms(query, "official", "independent")
            elif reason == "canonical_refetch_failure":
                candidate_urls.extend(str(url) for url in failure.get("next_candidate_urls") or [])
            applied_reasons.append(reason)
        if not applied_reasons:
            continue
        candidate["repair_reason"] = applied_reasons[0]
        candidate["repair_reasons"] = applied_reasons
        candidate["original_query"] = original_query
        candidate["inherited_constraints"] = inherited_constraints
        if "canonical_refetch_failure" in applied_reasons:
            candidate["candidate_urls"] = list(dict.fromkeys(candidate_urls))[
                :max_refetch_candidates
            ]
            if not candidate["candidate_urls"] and len(applied_reasons) == 1:
                continue
        repaired.append(candidate)

    if not repaired:
        return _stopped("repair_unavailable", current_progress_fingerprint)
    return {
        "should_repair": True,
        "pass_id": "pass-2",
        "facets": repaired,
        "trigger_count": len(repaired),
        "progress_fingerprint": current_progress_fingerprint,
        "stop_reason": "",
    }


def simplify_query(query: str, *, required_terms: list[str] | None = None) -> str:
    tokens = re.findall(r"[\w.+#-]+", query, flags=re.UNICODE)
    kept = [token for token in tokens if token.lower() not in _SIMPLIFY_STOP_WORDS]
    simplified = " ".join(kept) or query
    return _append_terms(simplified, *(required_terms or []))


def _append_terms(query: str, *terms: str) -> str:
    normalized = " ".join(query.lower().split())
    suffix = [term for term in terms if " ".join(term.lower().split()) not in normalized]
    return " ".join([query, *suffix]).strip()


def _stopped(reason: str, fingerprint: str) -> dict[str, Any]:
    return {
        "should_repair": False,
        "pass_id": "",
        "facets": [],
        "trigger_count": 0,
        "progress_fingerprint": fingerprint,
        "stop_reason": reason,
    }
