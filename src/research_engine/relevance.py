"""Dependency-free topical relevance and GitHub repository ranking."""

from __future__ import annotations

from datetime import date, datetime, timezone
import math
import re
from typing import Any
from urllib.parse import urlsplit


TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9.+#_-]*", re.IGNORECASE)


def tokenize(value: Any) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(str(value or ""))]


def score_text_relevance(
    query: str,
    *,
    title: str = "",
    text: str = "",
    topics: list[Any] | None = None,
) -> tuple[float, list[str]]:
    """Score query-token coverage with inspectable title/body/topic weights."""

    query_terms = list(dict.fromkeys(tokenize(query)))
    if not query_terms:
        return 0.0, []
    title_terms = set(tokenize(title))
    body_terms = set(tokenize(text))
    topic_terms = set(tokenize(" ".join(str(topic) for topic in topics or [])))
    matched: list[str] = []
    weighted = 0.0
    for term in query_terms:
        contribution = 0.0
        if term in title_terms:
            contribution = max(contribution, 1.0)
        if term in topic_terms:
            contribution = max(contribution, 0.8)
        if term in body_terms:
            contribution = max(contribution, 0.4)
        if contribution:
            matched.append(term)
            weighted += contribution
    return round(weighted / len(query_terms), 6), matched


def score_row_relevance(row: dict[str, Any], query: str) -> dict[str, Any]:
    """Add relevance fields without mutating evidence quality or validity fields."""

    query_terms = set(tokenize(query))
    title_terms = set(tokenize(row.get("title")))
    body_terms = set(tokenize(row.get("text") or row.get("text_excerpt")))
    entity_terms = set(
        tokenize(
            " ".join(
                str(row.get(key) or "")
                for key in ("company", "publisher", "organization", "repository")
            )
        )
    ) | set(tokenize(" ".join(str(value) for value in row.get("topics") or [])))
    facet_terms = set(tokenize(row.get("facet_id")))

    def coverage(terms: set[str]) -> float:
        return len(query_terms & terms) / len(query_terms) if query_terms else 0.0

    components = {
        "title": round(coverage(title_terms), 6),
        "body": round(coverage(body_terms), 6),
        "entity": round(coverage(entity_terms), 6),
        "facet": round(coverage(facet_terms), 6),
    }
    score = (
        components["title"] * 0.45
        + components["body"] * 0.35
        + components["entity"] * 0.15
        + components["facet"] * 0.05
    )
    enriched = dict(row)
    enriched["relevance_score"] = round(score, 6)
    enriched["relevance_components"] = components
    enriched["matched_query_terms"] = sorted(
        query_terms & (title_terms | body_terms | entity_terms | facet_terms)
    )
    return enriched


def build_relevance_preview(
    rows: list[dict[str, Any]], *, limit: int = 20
) -> list[dict[str, Any]]:
    """Return a high-signal preview with one row per deterministic source family."""

    ranked = sorted(
        (
            row
            for row in rows
            if row.get("claim_eligible") is not False
            and not row.get("is_duplicate")
            and float(row.get("relevance_score") or 0.0) > 0
        ),
        key=lambda row: (
            -float(row.get("relevance_score") or 0.0),
            -float(row.get("quality_score") or 0.0),
            str(row.get("evidence_id") or ""),
        ),
    )
    preview: list[dict[str, Any]] = []
    families: set[str] = set()
    for row in ranked:
        family = _source_family(row)
        if family in families:
            continue
        families.add(family)
        preview.append(row)
        if len(preview) >= max(0, limit):
            break
    return preview


def build_facet_coverage(
    rows: list[dict[str, Any]],
    *,
    query_plan: dict[str, Any],
    relevance_threshold: float = 0.15,
) -> dict[str, Any]:
    """Summarize yield for every required facet, including budget omissions."""

    facet_specs: dict[str, dict[str, Any]] = {
        str(facet_id): {
            "facet_id": str(facet_id),
            "required": True,
            "planned": False,
            "query_ids": [],
        }
        for facet_id in query_plan.get("required_facets") or []
        if str(facet_id)
    }
    for query in query_plan.get("queries") or []:
        facet_id = str(query.get("facet_id") or "")
        if not facet_id:
            continue
        spec = facet_specs.setdefault(
            facet_id,
            {
                "facet_id": facet_id,
                "required": False,
                "planned": False,
                "query_ids": [],
            },
        )
        spec["required"] = bool(spec["required"] or query.get("required"))
        spec["planned"] = True
        spec["query_ids"].append(str(query.get("query_id") or ""))

    facets: list[dict[str, Any]] = []
    for facet_id, spec in facet_specs.items():
        eligible = [
            row
            for row in rows
            if str(row.get("facet_id") or "") == facet_id
            and row.get("claim_eligible") is not False
            and not row.get("is_duplicate")
            and float(row.get("relevance_score") or 0.0) >= relevance_threshold
        ]
        facets.append(
            {
                **spec,
                "relevant_yield_count": len(eligible),
                "evidence_ids": [str(row.get("evidence_id") or "") for row in eligible],
                "status": (
                    "covered"
                    if eligible
                    else "missing"
                    if spec["planned"]
                    else "omitted_by_budget"
                ),
            }
        )
    missing = [row["facet_id"] for row in facets if row["required"] and not row["evidence_ids"]]
    omitted = [
        row["facet_id"]
        for row in facets
        if row["required"] and not row["planned"]
    ]
    required = [row for row in facets if row["required"]]
    return {
        "schema_version": "facet_coverage.v1",
        "required_facets": len(required),
        "required_facets_covered": len(required) - len(missing),
        "missing_required_facets": missing,
        "omitted_required_facets": omitted,
        "relevance_threshold": relevance_threshold,
        "facets": facets,
    }


def _source_family(row: dict[str, Any]) -> str:
    explicit = str(row.get("source_family") or row.get("publisher") or "").strip().lower()
    if explicit:
        return f"publisher:{explicit}"
    url = str(row.get("canonical_url") or row.get("final_url") or row.get("url") or "")
    host = urlsplit(url).netloc.lower().removeprefix("www.")
    return f"host:{host}" if host else f"row:{row.get('evidence_id') or id(row)}"


def rank_github_repositories(
    rows: list[dict[str, Any]],
    query: str,
    *,
    as_of: str | None = None,
) -> list[dict[str, Any]]:
    """Rank repositories while keeping topical match dominant and raw rank observable."""

    today = _as_of_date(as_of)
    ranked: list[dict[str, Any]] = []
    for index, original in enumerate(rows, start=1):
        row = dict(original)
        metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
        relevance, matched = score_text_relevance(
            query,
            title=str(row.get("title") or ""),
            text=str(row.get("text") or row.get("text_excerpt") or ""),
            topics=list(row.get("topics") or []),
        )
        adoption = min(24.0, 4.0 * math.log10(max(0, _number(metrics.get("stars"))) + 1))
        adoption += min(6.0, 2.0 * math.log10(max(0, _number(metrics.get("forks"))) + 1))
        recency = maintenance_recency(str(row.get("pushed_at") or row.get("updated_at") or ""), today)
        archived_penalty = -35.0 if row.get("archived") is True else 0.0
        final_score = relevance * 100.0 + adoption + recency + archived_penalty
        row["raw_api_rank"] = int(row.get("raw_api_rank") or index)
        row["relevance_score"] = relevance
        row["matched_query_terms"] = matched
        row["ranking_components"] = {
            "topical_relevance": round(relevance * 100.0, 4),
            "adoption": round(adoption, 4),
            "maintenance_recency": round(recency, 4),
            "archived_penalty": archived_penalty,
        }
        row["repository_rank_score"] = round(final_score, 4)
        ranked.append(row)
    ranked.sort(
        key=lambda row: (
            -float(row["repository_rank_score"]),
            int(row["raw_api_rank"]),
            str(row.get("title") or ""),
        )
    )
    for engine_rank, row in enumerate(ranked, start=1):
        row["engine_rank"] = engine_rank
    return ranked


def maintenance_recency(timestamp: str, as_of: date) -> float:
    if not timestamp:
        return 0.0
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        updated = parsed.astimezone(timezone.utc).date()
    except ValueError:
        return 0.0
    age = max(0, (as_of - updated).days)
    if age <= 30:
        return 8.0
    if age <= 180:
        return 6.0
    if age <= 365:
        return 4.0
    if age <= 730:
        return 2.0
    return 0.0


def _as_of_date(value: str | None) -> date:
    if value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            pass
    return datetime.now(timezone.utc).date()


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
