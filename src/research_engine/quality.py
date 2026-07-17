"""Deterministic evidence quality scoring and duplicate/conflict checks."""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import math
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from research_engine.models import utc_now
from research_engine.relevance import (
    build_facet_coverage,
    build_relevance_preview,
    score_row_relevance,
)


HIGH_RELIABILITY_CONNECTORS = {"finance_quote"}
MEDIUM_RELIABILITY_CONNECTORS = {"web_page", "rss"}
LOW_RELIABILITY_CONNECTORS = {"manual", "browser_audit", "logged_in_url"}

CONFIDENCE_ADJUSTMENTS = {
    "high": 0.15,
    "medium_high": 0.1,
    "medium": 0.0,
    "medium_low": -0.1,
    "low": -0.2,
}

CONFLICT_SETS = (
    {
        "id": "availability_pressure",
        "support": ("shortage", "tight supply", "scarce", "constrained", "capacity constraint"),
        "oppose": ("oversupply", "surplus", "glut", "excess inventory", "inventory correction"),
    },
    {
        "id": "directional_growth",
        "support": ("growth", "rising", "increase", "accelerating", "strong demand"),
        "oppose": ("decline", "falling", "decrease", "weak demand", "slowdown"),
    },
)

TEXT_CONTENT_TYPES = (
    "text/",
    "application/json",
    "application/ld+json",
    "application/xhtml+xml",
    "application/xml",
)
BLOCKED_CONTENT_MARKERS = (
    ("access_denied", "access denied you don't have permission"),
    ("blocked_by_network_security", "you've been blocked by network security"),
    ("browser_verification", "cf-browser-verification"),
    ("browser_verification", "please wait while we verify"),
    ("enable_javascript", "enable javascript and reload"),
    ("human_verification", "verify you are human"),
    ("platform_error", "something went wrong, but don't fret"),
    ("platform_error", "something went wrong, but don’t fret"),
    ("security_check", "just a moment checking your browser"),
    ("unusual_traffic", "unusual traffic from your computer network"),
)
LOGIN_WALL_PHRASES = (
    "continue with google",
    "continue with apple",
    "continue with phone",
    "sign in to continue",
    "log in to continue",
    "sign in to github",
    "log in to x",
    "sign in to x",
)
LOGIN_UI_MARKERS = (
    "username",
    "email address",
    "password",
    "forgot password",
    "create account",
    "sign up",
)
LOGIN_PATH_SEGMENTS = {"login", "signin", "sign-in", "session"}
MIN_VALID_WEB_TEXT_CHARS = 80
DISCOVERY_ONLY_SOURCE_KINDS = {"platform_search_page"}
DISCOVERY_ONLY_SOURCE_IDS = {"platform_search_pages"}


def enrich_rows_with_quality(
    rows: list[dict[str, Any]],
    *,
    topic: str,
    pack: dict[str, Any] | None = None,
    query_plan: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return evidence rows with quality metadata plus a run-level quality report."""

    enriched = [enrich_row(row, index=index) for index, row in enumerate(rows, start=1)]
    duplicate_clusters = build_duplicate_clusters(enriched)
    cluster_by_evidence_id = {
        evidence_id: cluster["cluster_id"]
        for cluster in duplicate_clusters
        for evidence_id in cluster["evidence_ids"]
    }
    row_by_evidence_id = {str(row.get("evidence_id") or ""): row for row in enriched}
    first_by_cluster = {
        cluster["cluster_id"]: max(
            cluster["evidence_ids"],
            key=lambda evidence_id: duplicate_preference(row_by_evidence_id.get(evidence_id, {})),
        )
        for cluster in duplicate_clusters
        if cluster.get("evidence_ids")
    }
    for row in enriched:
        cluster_id = cluster_by_evidence_id.get(str(row.get("evidence_id") or ""))
        row["duplicate_cluster_id"] = cluster_id
        row["is_duplicate"] = bool(
            cluster_id and first_by_cluster.get(cluster_id) != row.get("evidence_id")
        )

    queries_by_id = {
        str(query.get("query_id") or ""): str(query.get("query") or topic)
        for query in (query_plan or {}).get("queries") or []
    }
    enriched = [
        score_row_relevance(
            row,
            queries_by_id.get(str(row.get("query_id") or ""), topic),
        )
        for row in enriched
    ]
    facet_coverage = build_facet_coverage(enriched, query_plan=query_plan or {})
    relevance_preview = build_relevance_preview(enriched)

    conflict_flags = detect_conflict_flags(enriched, pack=pack)
    evidence_ids = [str(row.get("evidence_id") or "") for row in enriched]
    present_evidence_ids = [evidence_id for evidence_id in evidence_ids if evidence_id]
    evidence_id_collision_count = len(present_evidence_ids) - len(set(present_evidence_ids))
    scores = [float(row.get("quality_score") or 0.0) for row in enriched]
    tiers = Counter(str(row.get("quality_tier") or "unknown") for row in enriched)
    connectors = Counter(str(row.get("connector") or "unknown") for row in enriched)
    report = {
        "generated_at": utc_now(),
        "topic": topic,
        "pack_id": str((pack or {}).get("id") or "generic"),
        "row_count": len(enriched),
        "invalid_evidence_count": sum(1 for row in enriched if not is_evidence_eligible(row)),
        "claim_ineligible_count": sum(1 for row in enriched if not is_claim_eligible(row)),
        "unique_evidence_id_count": len(set(present_evidence_ids)),
        "evidence_id_collision_count": evidence_id_collision_count,
        "unique_evidence_count": len(enriched)
        - sum(1 for row in enriched if row.get("is_duplicate")),
        "unique_content_count": len(enriched)
        - sum(1 for row in enriched if row.get("is_duplicate")),
        "duplicate_cluster_count": len(duplicate_clusters),
        "average_quality_score": round(sum(scores) / len(scores), 3) if scores else 0.0,
        "tier_counts": dict(tiers),
        "connector_counts": dict(connectors),
        "duplicate_clusters": duplicate_clusters,
        "conflict_flags": conflict_flags,
        "facet_coverage": facet_coverage,
        "relevance_preview_evidence_ids": [
            str(row.get("evidence_id") or "") for row in relevance_preview
        ],
        "warnings": build_quality_warnings(
            enriched,
            duplicate_clusters,
            conflict_flags,
            evidence_id_collision_count=evidence_id_collision_count,
        ),
    }
    return enriched, report


def enrich_row(row: dict[str, Any], *, index: int) -> dict[str, Any]:
    enriched = dict(row)
    invalid_reasons = evidence_invalid_reasons(enriched)
    enriched["content_valid"] = not invalid_reasons
    enriched["content_invalid"] = bool(invalid_reasons)
    enriched["content_invalid_reasons"] = invalid_reasons
    enriched["claim_eligible"] = is_claim_eligible(enriched)
    score, reasons = score_row(enriched)
    enriched["quality_score"] = score
    enriched["quality_tier"] = quality_tier(score)
    enriched["quality_reasons"] = reasons
    enriched["dedupe_key"] = dedupe_key(enriched, index=index)
    enriched.setdefault("duplicate_cluster_id", None)
    enriched.setdefault("is_duplicate", False)
    return enriched


def score_row(row: dict[str, Any]) -> tuple[float, list[str]]:
    invalid_reasons = evidence_invalid_reasons(row)
    if invalid_reasons:
        return 0.0, ["invalid_content", *[f"invalid_{reason}" for reason in invalid_reasons]]

    connector = str(row.get("connector") or "").lower()
    confidence = str(row.get("source_confidence") or row.get("confidence") or "medium").lower()
    url = str(row.get("url") or row.get("source_url") or "")
    title = str(row.get("title") or "")
    text = str(row.get("text") or row.get("text_excerpt") or "")
    source_kind = str(row.get("source_kind") or row.get("entity_type") or "").lower()

    score = 0.5
    reasons: list[str] = []
    if connector in HIGH_RELIABILITY_CONNECTORS:
        score += 0.25
        reasons.append("high_reliability_connector")
    elif connector in MEDIUM_RELIABILITY_CONNECTORS:
        score += 0.12
        reasons.append("medium_reliability_connector")
    elif connector in LOW_RELIABILITY_CONNECTORS:
        score -= 0.05
        reasons.append("manual_or_logged_in_source")
    elif connector:
        reasons.append("connector_present")
    else:
        score -= 0.1
        reasons.append("missing_connector")

    score += CONFIDENCE_ADJUSTMENTS.get(confidence, 0.0)
    if confidence != "medium":
        reasons.append(f"source_confidence_{confidence}")
    if "official" in source_kind or "ir" in source_kind or "regulatory" in source_kind:
        score += 0.1
        reasons.append("source_kind_authoritative")
    if url.startswith("https://"):
        score += 0.05
        reasons.append("https_url")
    elif not url:
        score -= 0.12
        reasons.append("missing_url")
    if title:
        score += 0.03
    else:
        score -= 0.04
        reasons.append("missing_title")
    if len(text) >= 240:
        score += 0.05
        reasons.append("substantive_excerpt")
    elif not text:
        score -= 0.1
        reasons.append("missing_text")

    bounded = max(0.0, min(1.0, score))
    return round(bounded, 3), reasons


def quality_tier(score: float) -> str:
    if score >= 0.72:
        return "high"
    if score >= 0.45:
        return "medium"
    return "low"


def duplicate_preference(row: dict[str, Any]) -> tuple[int, int, float]:
    fitness = row.get("claim_fitness") or {}
    return (
        1 if is_evidence_eligible(row) else 0,
        1 if fitness.get("disposition") == "accepted" else 0,
        float(row.get("quality_score") or 0.0),
    )


def evidence_invalid_reasons(row: dict[str, Any]) -> list[str]:
    """Return deterministic reasons a row cannot support claims."""

    reasons = [str(reason) for reason in row.get("content_invalid_reasons") or [] if reason]
    if (row.get("content_invalid") is True or row.get("content_valid") is False) and not reasons:
        reasons.append("explicit_invalid")
    if row.get("access_blocked") is True and not reasons:
        reasons.append("access_blocked")

    status = row.get("http_status")
    try:
        if status is not None and int(status) >= 400:
            reasons.append(f"http_status_{int(status)}")
    except (TypeError, ValueError):
        reasons.append("invalid_http_status")

    connector = str(row.get("connector") or "").lower()
    is_web_fetch = connector == "web_page" or row.get("transport_fetched") is True
    has_fetch_metadata = any(
        key in row for key in ("http_status", "content_type", "final_url", "access_blocked")
    )
    if is_web_fetch:
        content_type = str(row.get("content_type") or "").lower().split(";", 1)[0].strip()
        extracted_pdf = content_type == "application/pdf" and row.get("extracted_content") is True
        if (
            content_type
            and not content_type.startswith(TEXT_CONTENT_TYPES)
            and not extracted_pdf
        ):
            reasons.append(f"unsupported_content_type_{content_type}")

        text = normalize_text(str(row.get("text") or row.get("text_excerpt") or ""))
        for reason, marker in BLOCKED_CONTENT_MARKERS:
            if marker in text:
                reasons.append(reason)
        login_phrases = [marker for marker in LOGIN_WALL_PHRASES if marker in text]
        login_ui = [marker for marker in LOGIN_UI_MARKERS if marker in text]
        url = str(row.get("final_url") or row.get("url") or row.get("source_url") or "")
        path_segments = {
            segment for segment in urlsplit(url).path.lower().split("/") if segment
        }
        login_url = bool(path_segments & LOGIN_PATH_SEGMENTS)
        if (
            (login_url and login_phrases)
            or len(login_phrases) >= 2
            or (login_phrases and len(login_ui) >= 3)
        ):
            reasons.append("login_wall")
        if (
            len(text) < 1000
            and "captcha" in text
            and any(marker in text for marker in ("complete the captcha", "captcha challenge"))
        ):
            reasons.append("captcha")
        if has_fetch_metadata and len(text) < MIN_VALID_WEB_TEXT_CHARS:
            reasons.append("insufficient_text")

    return list(dict.fromkeys(reasons))


def is_evidence_eligible(row: dict[str, Any]) -> bool:
    return not evidence_invalid_reasons(row)


def is_claim_eligible(row: dict[str, Any]) -> bool:
    if not is_evidence_eligible(row):
        return False
    source_kind = str(row.get("source_kind") or "").lower()
    source_id = str(row.get("source_id") or "").lower()
    source_class = str(row.get("source_class") or "").lower()
    claim_fitness = row.get("claim_fitness")
    if isinstance(claim_fitness, dict) and claim_fitness.get("disposition") != "accepted":
        return False
    freshness_status = str(row.get("freshness_status") or "").lower()
    if freshness_status in {"stale", "future_dated"}:
        return False
    try:
        if row.get("age_days") is not None:
            age_days = float(row["age_days"])
            if not math.isfinite(age_days) or age_days < 0:
                return False
    except (TypeError, ValueError):
        return False
    if row.get("freshness_window_days") is not None and freshness_status != "fresh":
        return False
    return (
        source_kind not in DISCOVERY_ONLY_SOURCE_KINDS
        and source_id not in DISCOVERY_ONLY_SOURCE_IDS
        and source_class != "discovery_only"
    )


def dedupe_key(row: dict[str, Any], *, index: int) -> str:
    url = str(row.get("url") or row.get("source_url") or "").strip()
    if url:
        return f"url:{canonicalize_url(url)}"
    title = normalize_text(str(row.get("title") or ""))
    text = normalize_text(str(row.get("text") or row.get("text_excerpt") or ""))
    if title or text:
        digest = hashlib.sha1(f"{title}|{text[:240]}".encode("utf-8")).hexdigest()[:16]
        return f"text:{digest}"
    return f"row:{index:04d}"


def canonicalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    path = re.sub(r"/+$", "", parsed.path or "/")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def build_duplicate_clusters(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows_by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("source_class") == "discovery_only" or (
            row.get("claim_fitness") or {}
        ).get("disposition") == "discovery_only":
            continue
        rows_by_key[str(row.get("dedupe_key") or "")].append(row)

    clusters: list[dict[str, Any]] = []
    for index, (key, values) in enumerate(sorted(rows_by_key.items()), start=1):
        if len(values) < 2:
            continue
        clusters.append(
            {
                "cluster_id": f"dup-{index:04d}",
                "dedupe_key": key,
                "evidence_ids": [str(row.get("evidence_id") or "") for row in values],
                "titles": [str(row.get("title") or "") for row in values[:3] if row.get("title")],
                "reason": "same canonical URL" if key.startswith("url:") else "same title/text fingerprint",
            }
        )
    return clusters


def detect_conflict_flags(
    rows: list[dict[str, Any]],
    *,
    pack: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    configured_sets = ((pack or {}).get("quality_rules") or {}).get("conflict_sets")
    conflict_sets = configured_sets if isinstance(configured_sets, list) else CONFLICT_SETS
    flags: list[dict[str, Any]] = []
    for conflict_set in conflict_sets:
        if not isinstance(conflict_set, dict):
            continue
        support_terms = [str(term).lower() for term in conflict_set.get("support") or []]
        oppose_terms = [str(term).lower() for term in conflict_set.get("oppose") or []]
        support_ids = match_rows(rows, support_terms)
        oppose_ids = match_rows(rows, oppose_terms)
        if support_ids and oppose_ids:
            flags.append(
                {
                    "flag_id": str(conflict_set.get("id") or f"conflict-{len(flags) + 1:02d}"),
                    "support_evidence_ids": support_ids[:12],
                    "oppose_evidence_ids": oppose_ids[:12],
                    "support_terms": support_terms,
                    "oppose_terms": oppose_terms,
                    "note": "Collected evidence contains directionally opposing terms; review before synthesis.",
                }
            )
    return flags


def match_rows(rows: list[dict[str, Any]], terms: list[str]) -> list[str]:
    matched: list[str] = []
    for row in rows:
        if not is_claim_eligible(row):
            continue
        text = normalize_text(
            " ".join(
                str(value or "")
                for value in (row.get("title"), row.get("text"), row.get("text_excerpt"))
            )
        )
        if any(term and term in text for term in terms):
            evidence_id = str(row.get("evidence_id") or "")
            if evidence_id:
                matched.append(evidence_id)
    return matched


def build_quality_warnings(
    rows: list[dict[str, Any]],
    duplicate_clusters: list[dict[str, Any]],
    conflict_flags: list[dict[str, Any]],
    *,
    evidence_id_collision_count: int = 0,
) -> list[str]:
    warnings: list[str] = []
    invalid_rows = [row for row in rows if not is_evidence_eligible(row)]
    if invalid_rows:
        warnings.append(f"{len(invalid_rows)} invalid evidence row(s) excluded from claims.")
    discovery_rows = [
        row for row in rows if is_evidence_eligible(row) and not is_claim_eligible(row)
    ]
    if discovery_rows:
        warnings.append(
            f"{len(discovery_rows)} discovery-only evidence row(s) excluded from claims."
        )
    if evidence_id_collision_count:
        warnings.append(
            f"{evidence_id_collision_count} evidence id collision(s) detected; normalize before synthesis."
        )
    if duplicate_clusters:
        duplicate_rows = sum(len(cluster.get("evidence_ids") or []) - 1 for cluster in duplicate_clusters)
        warnings.append(f"{duplicate_rows} duplicate evidence row(s) detected across {len(duplicate_clusters)} cluster(s).")
    low_rows = [row for row in rows if row.get("quality_tier") == "low"]
    if low_rows:
        warnings.append(f"{len(low_rows)} low-quality evidence row(s) need source review.")
    if conflict_flags:
        warnings.append(f"{len(conflict_flags)} directional conflict flag(s) need review before synthesis.")
    return warnings
