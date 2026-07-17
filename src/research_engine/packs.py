"""Research pack loading and topic selection."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


DEFAULT_PACK_ID = "generic"
PROJECT_PACK_DIR = Path.cwd() / "packs"
PACKAGE_PACK_DIR = Path(__file__).resolve().parent / "default_packs"
PROFILE_REQUIRED_FACETS: dict[str, frozenset[str]] = {
    "technical": frozenset(
        {"official_docs", "repositories", "releases", "architecture", "performance", "limitations"}
    ),
    "market_landscape": frozenset(
        {
            "market_definition",
            "companies_products",
            "pricing",
            "demand",
            "competition",
            "constraints",
            "contrary_evidence",
        }
    ),
    "job_market": frozenset(
        {"active_openings", "company_coverage", "role_terms", "geography", "skills", "compensation"}
    ),
}


def load_research_packs(pack_dir: Path | None = None) -> list[dict[str, Any]]:
    pack_dirs = [PACKAGE_PACK_DIR]
    overlay_dir = pack_dir or PROJECT_PACK_DIR
    if overlay_dir.exists() and overlay_dir.resolve() != PACKAGE_PACK_DIR.resolve():
        pack_dirs.append(overlay_dir)
    packs_by_id: dict[str, dict[str, Any]] = {}
    for resolved in pack_dirs:
        for path in sorted(resolved.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                pack = normalize_pack(payload, path=path)
                packs_by_id[str(pack["id"])] = pack
    if DEFAULT_PACK_ID not in packs_by_id:
        packs_by_id[DEFAULT_PACK_ID] = normalize_pack({"id": DEFAULT_PACK_ID}, path=None)
    return list(packs_by_id.values())


def select_research_pack(
    topic: str,
    *,
    pack_dir: Path | None = None,
    pack_id: str | None = None,
) -> dict[str, Any]:
    packs = load_research_packs(pack_dir)
    if pack_id:
        for pack in packs:
            if pack.get("id") == pack_id:
                return pack
        raise ValueError(f"unknown research pack: {pack_id}")
    generic = next(pack for pack in packs if pack.get("id") == DEFAULT_PACK_ID)
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for index, pack in enumerate(packs):
        if pack.get("id") == DEFAULT_PACK_ID:
            continue
        score = score_pack_match(topic, pack)
        if score >= int(pack.get("min_match_score") or 1):
            scored.append((score, -index, pack))
    return max(scored, key=lambda item: (item[0], item[1]))[2] if scored else generic


def pack_summary(pack: dict[str, Any]) -> dict[str, str]:
    return {
        "id": str(pack.get("id") or DEFAULT_PACK_ID),
        "label": str(pack.get("label") or pack.get("id") or DEFAULT_PACK_ID),
        "intent": str(pack.get("intent") or "general_research"),
        "profile": str(pack.get("profile") or pack.get("id") or DEFAULT_PACK_ID),
    }


def build_pack_queries(topic: str, pack: dict[str, Any]) -> list[dict[str, str]]:
    facet_queries = [
        {
            "tier": str(facet.get("id") or facet.get("facet_id") or "public_connector"),
            "query": str(template).format(topic=topic),
        }
        for facet in pack.get("facets") or []
        if isinstance(facet, dict)
        for template in _facet_templates(facet)
    ]
    if facet_queries:
        return facet_queries
    templates = pack.get("query_templates") or []
    if not templates:
        return [{"tier": "public_connector", "query": topic}]
    return [
        {
            "tier": str(template.get("tier") or "public_connector"),
            "query": str(template.get("template") or "{topic}").format(topic=topic),
        }
        for template in templates
        if isinstance(template, dict)
    ]


def score_pack_match(topic: str, pack: dict[str, Any]) -> int:
    return sum(
        max(1, len(str(term).split()))
        for term in pack.get("match_terms") or []
        if topic_matches_term(topic, str(term))
    )


def topic_matches_term(topic: str, term: str) -> bool:
    topic_text = topic.lower()
    term_text = term.lower().strip()
    if not term_text:
        return False
    if re.fullmatch(r"[a-z0-9.$-]{1,4}", term_text):
        pattern = rf"(?<![a-z0-9]){re.escape(term_text)}(?![a-z0-9])"
        return re.search(pattern, topic_text) is not None
    return term_text in topic_text


def normalize_pack(payload: dict[str, Any], *, path: Path | None) -> dict[str, Any]:
    pack = dict(payload)
    pack.setdefault("id", DEFAULT_PACK_ID)
    pack.setdefault("label", pack["id"])
    pack.setdefault("profile", pack["id"])
    pack.setdefault("intent", "general_research")
    pack.setdefault("match_terms", [])
    pack.setdefault("query_templates", [])
    pack.setdefault("facets", [])
    pack.setdefault("sources", [])
    pack.setdefault("claim_specs", [])
    pack.setdefault("matrix_nodes", [])
    pack.setdefault("matrix_entities", {})
    pack.setdefault("decision_rules", {})
    validate_pack(pack, path=path)
    if path:
        pack["_pack_path"] = str(path)
    return pack


def validate_pack(pack: dict[str, Any], *, path: Path | None = None) -> None:
    """Reject malformed profile contracts before they reach planning."""

    prefix = f"{path}: " if path else ""
    pack_id = str(pack.get("id") or "").strip()
    if not pack_id:
        raise ValueError(prefix + "pack id must be non-empty")
    facets = pack.get("facets")
    if not isinstance(facets, list):
        raise ValueError(prefix + "pack facets must be a list")

    facet_ids: list[str] = []
    for facet in facets:
        if not isinstance(facet, dict):
            raise ValueError(prefix + "pack facets must contain objects")
        facet_id = str(facet.get("id") or facet.get("facet_id") or "").strip()
        if not facet_id:
            raise ValueError(prefix + "facet id must be non-empty")
        facet_ids.append(facet_id)
        if not _facet_templates(facet):
            raise ValueError(prefix + f"facet {facet_id} requires query_templates")
        source_types = facet.get("source_types")
        if not isinstance(source_types, list) or not all(
            isinstance(value, str) and value.strip() for value in source_types
        ):
            raise ValueError(prefix + f"facet {facet_id} requires source_types")
        if "required" in facet and not isinstance(facet["required"], bool):
            raise ValueError(prefix + f"facet {facet_id} required must be boolean")
        freshness = facet.get("freshness_window_days")
        if freshness is not None and (not isinstance(freshness, int) or freshness < 0):
            raise ValueError(prefix + f"facet {facet_id} freshness_window_days must be non-negative")
    if len(facet_ids) != len(set(facet_ids)):
        raise ValueError(prefix + f"{pack_id} pack facet ids must be unique")

    required = PROFILE_REQUIRED_FACETS.get(str(pack.get("profile") or ""))
    missing = sorted((required or set()) - set(facet_ids))
    if missing:
        raise ValueError(prefix + f"{pack_id} pack missing required facets: {', '.join(missing)}")


def _facet_templates(facet: dict[str, Any]) -> list[str]:
    values = facet.get("query_templates") or []
    if isinstance(values, str):
        values = [values]
    return [str(value) for value in values if isinstance(value, str) and value.strip()]
