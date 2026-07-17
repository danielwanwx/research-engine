"""Independent source-family and claim-polarity chains."""

from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import urlsplit

from research_engine.quality import is_claim_eligible


_SUPPORT = {"for", "positive", "support", "supported", "supports"}
_OPPOSE = {"against", "negative", "oppose", "opposed", "opposes"}


def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9.-]+", "-", str(value or "").lower()).strip("-")


def build_independence_key(row: dict[str, Any]) -> str:
    """Return the strongest deterministic owner/repository/host family available."""

    explicit = row.get("source_family") or row.get("syndication_origin")
    if explicit:
        return f"family:{_key(explicit)}"
    organization = row.get("organization") or row.get("publisher_organization")
    if organization:
        return f"organization:{_key(organization)}"
    if row.get("publisher"):
        return f"publisher:{_key(row['publisher'])}"

    url = str(row.get("canonical_url") or row.get("final_url") or row.get("url") or "")
    parsed = urlsplit(url)
    host = parsed.netloc.lower().split("@")[-1].split(":")[0].removeprefix("www.")
    parts = [part for part in parsed.path.split("/") if part]
    if host in {"github.com", "gitlab.com"} and len(parts) >= 2:
        return f"repo:{host}/{_key(parts[0])}/{_key(parts[1])}"
    if host:
        return f"host:{host}"
    return f"row:{_key(row.get('evidence_id') or row.get('title') or 'unknown')}"


def build_claim_chains(
    rows: list[dict[str, Any]],
    *,
    claim_id: str,
    min_support: int = 2,
) -> dict[str, Any]:
    """Build non-overlapping independent support and opposition chains."""

    if min_support < 1:
        raise ValueError("min_support must be positive")

    support_rows = [row for row in rows if _polarity(row, claim_id) == "support"]
    opposition_rows = [row for row in rows if _polarity(row, claim_id) == "oppose"]
    support = _independent_rows(support_rows)
    support_ids = {str(row.get("evidence_id") or "") for row in support}
    support_keys = {build_independence_key(row) for row in support}
    opposition = _independent_rows(
        opposition_rows,
        excluded_ids=support_ids,
        excluded_keys=support_keys,
    )

    if support and opposition:
        stance, ceiling = "conflicted", "medium"
    elif len(support) >= min_support:
        stance, ceiling = "supported", "high"
    elif len(opposition) >= min_support:
        stance, ceiling = "opposed", "high"
    else:
        stance, ceiling = "needs_more_evidence", "low"
    return {
        "claim_id": claim_id,
        "stance": stance,
        "confidence_ceiling": ceiling,
        "minimum_independent_support": min_support,
        "support_chain": _chain(support),
        "opposition_chain": _chain(opposition),
    }


def _polarity(row: dict[str, Any], claim_id: str) -> str:
    if not is_claim_eligible(row) or row.get("claim_eligible") is False:
        return ""
    mapping = row.get("claim_polarities")
    value = mapping.get(claim_id) if isinstance(mapping, dict) else None
    value = str(value or row.get("claim_polarity") or row.get("polarity") or "").lower()
    if value in _SUPPORT:
        return "support"
    if value in _OPPOSE:
        return "oppose"
    return ""


def _independent_rows(
    rows: list[dict[str, Any]],
    *,
    excluded_ids: set[str] | None = None,
    excluded_keys: set[str] | None = None,
) -> list[dict[str, Any]]:
    used_ids = set(excluded_ids or set())
    used_keys = set(excluded_keys or set())
    used_hashes: set[str] = set()
    accepted: list[dict[str, Any]] = []
    for row in rows:
        evidence_id = str(row.get("evidence_id") or "")
        key = build_independence_key(row)
        content_hash = str(row.get("content_hash") or "") or hashlib.sha256(
            " ".join(str(row.get("text") or "").lower().split()).encode("utf-8")
        ).hexdigest()
        if not evidence_id or evidence_id in used_ids or key in used_keys or content_hash in used_hashes:
            continue
        accepted.append(row)
        used_ids.add(evidence_id)
        used_keys.add(key)
        used_hashes.add(content_hash)
    return accepted


def _chain(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "evidence_ids": [str(row.get("evidence_id") or "") for row in rows],
        "independence_keys": [build_independence_key(row) for row in rows],
        "independent_source_count": len(rows),
    }
