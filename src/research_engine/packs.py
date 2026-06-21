"""Research pack loading and topic selection."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


DEFAULT_PACK_ID = "generic"
PROJECT_PACK_DIR = Path.cwd() / "packs"
PACKAGE_PACK_DIR = Path(__file__).resolve().parent / "default_packs"


def load_research_packs(pack_dir: Path | None = None) -> list[dict[str, Any]]:
    resolved = pack_dir or (PROJECT_PACK_DIR if PROJECT_PACK_DIR.exists() else PACKAGE_PACK_DIR)
    packs: list[dict[str, Any]] = []
    if resolved.exists():
        for path in sorted(resolved.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                packs.append(normalize_pack(payload, path=path))
    if not any(pack.get("id") == DEFAULT_PACK_ID for pack in packs):
        packs.append(normalize_pack({"id": DEFAULT_PACK_ID}, path=None))
    return packs


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
        1
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
    pack.setdefault("sources", [])
    pack.setdefault("claim_specs", [])
    pack.setdefault("matrix_nodes", [])
    pack.setdefault("matrix_entities", {})
    pack.setdefault("decision_rules", {})
    if path:
        pack["_pack_path"] = str(path)
    return pack
