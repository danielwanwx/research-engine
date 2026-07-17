"""Deterministic research profile and facet planning."""

from __future__ import annotations

from datetime import date
import re
from typing import Any

from research_engine.models import CollectionRequest


DEPTH_BUDGETS: dict[str, dict[str, int]] = {
    "quick": {
        "max_queries": 3,
        "max_results_per_query": 5,
        "max_canonical_refetches": 8,
        "max_repair_passes": 1,
    },
    "deep": {
        "max_queries": 8,
        "max_results_per_query": 8,
        "max_canonical_refetches": 24,
        "max_repair_passes": 1,
    },
    "audit": {
        "max_queries": 12,
        "max_results_per_query": 10,
        "max_canonical_refetches": 40,
        "max_repair_passes": 1,
    },
}

PROFILE_FACETS: dict[str, tuple[tuple[str, str, str, int | None], ...]] = {
    "generic": (
        ("overview", "{topic} overview", "web_search", None),
        ("primary_sources", "{topic} official primary sources", "web_search", None),
        ("current_evidence", "{topic} current evidence", "web_search", 365),
        ("alternatives", "{topic} alternatives", "web_search", None),
        ("risks", "{topic} risks limitations counterevidence", "web_search", None),
    ),
    "technical": (
        ("official_docs", "{topic} official documentation", "web_search", None),
        ("repositories", "{topic} GitHub", "github_public_search", None),
        ("releases", "{topic} releases maintenance", "web_search", 365),
        ("architecture", "{topic} architecture design", "web_search", None),
        ("performance", "{topic} performance benchmark", "web_search", 365),
        ("limitations", "{topic} limitations issues", "web_search", None),
    ),
    "market_landscape": (
        ("market_definition", "{topic} market definition", "web_search", None),
        ("companies_products", "{topic} companies products", "web_search", 365),
        ("pricing", "{topic} official pricing monetization", "web_search", 180),
        ("demand", "{topic} demand signals", "web_search", 180),
        ("competition", "{topic} competition alternatives", "web_search", 365),
        ("constraints", "{topic} regulation constraints", "web_search", 365),
        ("contrary_evidence", "{topic} risks contrary evidence", "web_search", 365),
    ),
    "job_market": (
        ("active_openings", "{topic} official careers openings", "web_search", 30),
        ("company_coverage", "{topic} companies hiring", "web_search", 30),
        ("role_terms", "{topic} role titles", "web_search", 90),
        ("geography", "{topic} locations", "web_search", 30),
        ("skills", "{topic} required skills", "web_search", 90),
        ("compensation", "{topic} published compensation", "web_search", 90),
    ),
}

PROFILE_ALIASES = {
    "market-landscape": "market_landscape",
    "job-market": "job_market",
}
ALLOWED_PROFILES = frozenset(PROFILE_FACETS)
SOURCE_CONNECTORS = {
    "web_search": "web_search",
    "github_public_search": "github_public_search",
    "official_job_discovery": "official_job_discovery",
}


def validate_research_scope(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a dependency-free ``research_scope.v1`` mapping."""

    if not isinstance(payload, dict) or payload.get("schema_version") != "research_scope.v1":
        raise ValueError("scope schema_version must be research_scope.v1")
    profile = normalize_profile(payload.get("profile"))
    if profile not in ALLOWED_PROFILES:
        raise ValueError(f"unsupported research profile: {profile or '<empty>'}")
    as_of = str(payload.get("as_of") or "").strip()
    if as_of:
        try:
            date.fromisoformat(as_of)
        except ValueError as exc:
            raise ValueError("scope as_of must be YYYY-MM-DD") from exc
    filters = payload.get("filters") or {}
    if not isinstance(filters, dict):
        raise ValueError("scope filters must be an object")
    normalized_filters = {
        str(key): [str(value).strip() for value in values if str(value).strip()]
        for key, values in filters.items()
        if isinstance(values, list)
    }
    if profile == "job_market":
        normalized_filters.setdefault("geography", ["US"])
        required = ("geography", "role_terms", "levels", "companies")
        missing = [key for key in required if not normalized_filters.get(key)]
        if missing:
            raise ValueError(f"job_market scope requires non-empty filters: {', '.join(missing)}")
        multi_axes = [
            key
            for key in ("geography", "role_terms", "levels")
            if len(normalized_filters[key]) != 1
        ]
        if multi_axes:
            raise ValueError(
                "job_market quantitative filters must be singleton: "
                + ", ".join(multi_axes)
            )
    normalized = {
        "schema_version": "research_scope.v1",
        "profile": profile,
        "as_of": as_of,
        "filters": normalized_filters,
    }
    if profile == "job_market":
        normalized["quantitative_axis_policy"] = {
            "companies": "bounded_multi",
            "geography": "singleton",
            "levels": "singleton",
            "role_terms": "singleton",
        }
    return normalized


def normalize_profile(value: Any) -> str:
    profile = str(value or "").strip().lower().replace(" ", "_")
    return PROFILE_ALIASES.get(profile, profile)


def build_repair_constraints(
    topic: str,
    *,
    scope: dict[str, Any] | None,
    comparison_projects: list[str] | None = None,
) -> list[str]:
    """Return explicit scope and time terms that repair must retain."""

    values = [
        str(value)
        for items in ((scope or {}).get("filters") or {}).values()
        for value in items
    ]
    values.extend(comparison_projects or [])
    values.extend(
        re.findall(
            r"\b(?:20\d{2}(?:-\d{2}(?:-\d{2})?)?|Q[1-4]|H[12]|"
            r"January|February|March|April|May|June|July|August|September|"
            r"October|November|December)\b",
            topic,
            flags=re.IGNORECASE,
        )
    )
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def route_profile(
    *,
    scope: dict[str, Any] | None = None,
    pack: dict[str, Any] | None = None,
) -> str:
    """Select a profile with explicit scope taking precedence over pack intent."""

    scoped = normalize_profile((scope or {}).get("profile"))
    if scoped in ALLOWED_PROFILES:
        return scoped
    packed = normalize_profile((pack or {}).get("profile"))
    if packed in ALLOWED_PROFILES:
        return packed
    intent = str((pack or {}).get("intent") or "").lower()
    if "technical" in intent:
        return "technical"
    if "job_market" in intent or "job market" in intent:
        return "job_market"
    if "market" in intent and "financial" not in intent:
        return "market_landscape"
    return "generic"


def build_query_plan(
    topic: str,
    *,
    pack: dict[str, Any] | None = None,
    depth: str = "deep",
    scope: dict[str, Any] | None = None,
    search_provider: str = "anysearch",
    search_endpoint: str = "",
) -> dict[str, Any]:
    """Build a bounded, serializable facet/query plan."""

    if depth not in DEPTH_BUDGETS:
        raise ValueError(f"unsupported research depth: {depth}")
    validated_scope = validate_research_scope(scope) if scope else None
    profile = route_profile(scope=validated_scope, pack=pack)
    budget = dict(DEPTH_BUDGETS[depth])
    pack_profile = normalize_profile((pack or {}).get("profile"))
    comparison_projects = technical_projects(topic, scope=validated_scope)
    repair_constraints = build_repair_constraints(
        topic,
        scope=validated_scope,
        comparison_projects=comparison_projects,
    )
    use_pack_queries = (not validated_scope or pack_profile == profile) and not (
        profile == "technical" and len(comparison_projects) >= 2
    )
    candidates = (
        (_pack_queries(topic, pack or {}) if use_pack_queries else [])
        or _profile_queries(topic, profile, scope=validated_scope)
    )
    all_facets = list(
        dict.fromkeys(
            slug(str(candidate.get("facet_id") or f"facet-{index}"))
            for index, candidate in enumerate(candidates, start=1)
        )
    )
    required_facets = list(
        dict.fromkeys(
            slug(str(candidate.get("facet_id") or f"facet-{index}"))
            for index, candidate in enumerate(candidates, start=1)
            if bool(candidate.get("required", True))
        )
    )
    queries: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates[: budget["max_queries"]], start=1):
        source_types = [str(value) for value in candidate.get("source_types") or ["web_search"]]
        queries.append(
            {
                "facet_id": slug(str(candidate.get("facet_id") or f"facet-{index}")),
                "query_id": f"q-{index:04d}",
                "query": str(candidate.get("query") or topic),
                "source_types": list(dict.fromkeys(source_types)),
                "required": bool(candidate.get("required", True)),
                "freshness_window_days": candidate.get("freshness_window_days"),
                "max_results": min(
                    max(1, int(candidate.get("max_results") or budget["max_results_per_query"])),
                    budget["max_results_per_query"],
                ),
                "repair_constraints": repair_constraints,
                "status": "planned",
            }
        )
    facets = list(dict.fromkeys(item["facet_id"] for item in queries))
    omitted_required_facets = [facet for facet in required_facets if facet not in facets]
    return {
        "schema_version": "query_plan.v2",
        "profile": profile,
        "depth": depth,
        "search_provider": search_provider,
        "search_endpoint": search_endpoint,
        "third_party_query_boundary": search_provider not in {"none", ""},
        "budget": budget,
        "all_facets": all_facets,
        "required_facets": required_facets,
        "facets": facets,
        "omitted_required_facets": omitted_required_facets,
        "queries": queries,
        "scope": validated_scope,
        "claim_context": claim_context(profile, validated_scope),
        "quantitative_claims_allowed": profile != "job_market" or bool(validated_scope),
        "job_company_coverage": job_company_coverage(
            profile,
            validated_scope,
            depth=depth,
        ),
    }


def claim_context(
    profile: str,
    scope: dict[str, Any] | None,
) -> dict[str, Any]:
    """Expose available market definition, geography, and as-of constraints."""

    if profile != "market_landscape" or not scope:
        return {}
    filters = scope.get("filters") or {}
    context: dict[str, Any] = {}
    if scope.get("as_of"):
        context["as_of"] = scope["as_of"]
    for key in ("definition", "geography"):
        if filters.get(key):
            context[key] = list(filters[key])
    return context


def job_company_coverage(
    profile: str,
    scope: dict[str, Any] | None,
    *,
    depth: str,
) -> dict[str, list[str]]:
    if profile != "job_market" or not scope:
        return {}
    requested = [str(value) for value in (scope.get("filters") or {}).get("companies") or []]
    limit = {"quick": 5, "deep": 12, "audit": 20}[depth]
    return {
        "requested": requested,
        "planned": requested[:limit],
        "unsupported_by_depth_budget": requested[limit:],
    }


def collection_requests_from_plan(
    plan: dict[str, Any],
    *,
    topic: str,
    run_date: str,
) -> list[CollectionRequest]:
    """Convert planned queries to existing connector requests without losing lineage."""

    requests: list[CollectionRequest] = []
    for item in plan.get("queries") or []:
        source_types = item.get("source_types") or ["web_search"]
        for source_type in source_types:
            connector = SOURCE_CONNECTORS.get(str(source_type), str(source_type))
            source = {
                "source_id": f"plan-{item['query_id']}-{connector}",
                "connector": connector,
                "query": item["query"],
                "query_id": item["query_id"],
                "facet_id": item["facet_id"],
                "pass_id": "pass-1",
                "required": item.get("required", True),
                "freshness_window_days": item.get("freshness_window_days"),
            }
            if connector == "web_search":
                source["provider"] = plan.get("search_provider") or "none"
                if source["provider"] == "anysearch":
                    source["endpoint"] = "https://api.anysearch.com/v1/search"
                elif plan.get("search_endpoint"):
                    source["endpoint"] = plan["search_endpoint"]
            elif connector == "github_public_search":
                source["endpoint"] = "https://api.github.com/search/repositories"
            requests.append(
                CollectionRequest(
                    source=source,
                    topic=topic,
                    run_date=run_date,
                    depth=str(plan.get("depth") or "deep"),
                    max_results=int(item.get("max_results") or 1),
                )
            )
    return requests


def _pack_queries(topic: str, pack: dict[str, Any]) -> list[dict[str, Any]]:
    queries: list[dict[str, Any]] = []
    facets = pack.get("facets") or []
    for index, facet in enumerate(facets, start=1):
        if not isinstance(facet, dict):
            continue
        templates = facet.get("query_templates") or [facet.get("template") or "{topic}"]
        if isinstance(templates, str):
            templates = [templates]
        for template in templates:
            queries.append(
                {
                    "facet_id": facet.get("id") or facet.get("facet_id") or f"facet-{index}",
                    "query": str(template).format(topic=topic),
                    "source_types": facet.get("source_types") or ["web_search"],
                    "required": facet.get("required", True),
                    "freshness_window_days": facet.get("freshness_window_days"),
                    "max_results": facet.get("max_results"),
                }
            )
    if queries:
        return queries
    for index, template in enumerate(pack.get("query_templates") or [], start=1):
        if not isinstance(template, dict):
            continue
        tier = str(template.get("tier") or f"facet-{index}")
        queries.append(
            {
                "facet_id": tier,
                "query": str(template.get("template") or "{topic}").format(topic=topic),
                "source_types": template.get("source_types") or ["web_search"],
                "required": template.get("required", True),
                "freshness_window_days": template.get("freshness_window_days"),
                "max_results": template.get("max_results"),
            }
        )
    return queries


def _profile_queries(
    topic: str,
    profile: str,
    *,
    scope: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if profile == "technical":
        projects = technical_projects(topic, scope=scope)
        if len(projects) >= 2:
            queries: list[dict[str, Any]] = []
            for project in projects[:3]:
                project_id = slug(project)
                queries.append(
                    {
                        "facet_id": f"project_{project_id}_repository",
                        "query": f"{project} in:name",
                        "source_types": ["github_public_search"],
                        "required": True,
                        "freshness_window_days": None,
                    }
                )
            for project in projects[:3]:
                project_id = slug(project)
                queries.append(
                    {
                        "facet_id": f"project_{project_id}_official_docs",
                        "query": f"{project} official documentation",
                        "source_types": ["web_search"],
                        "required": True,
                        "freshness_window_days": None,
                    }
                )
            queries.extend(
                [
                    {
                        "facet_id": "comparison_benchmarks",
                        "query": f"{topic} benchmark performance",
                        "source_types": ["web_search"],
                        "required": True,
                        "freshness_window_days": 365,
                    },
                    {
                        "facet_id": "comparison_limitations",
                        "query": f"{topic} limitations issues",
                        "source_types": ["web_search"],
                        "required": True,
                        "freshness_window_days": None,
                    },
                ]
            )
            return queries
    return [
        {
            "facet_id": facet_id,
            "query": template.format(topic=topic),
            "source_types": [source_type],
            "required": True,
            "freshness_window_days": freshness_window_days,
        }
        for facet_id, template, source_type, freshness_window_days in PROFILE_FACETS[profile]
    ]


def technical_projects(topic: str, *, scope: dict[str, Any] | None = None) -> list[str]:
    configured = ((scope or {}).get("filters") or {}).get("projects") or []
    projects = [str(value).strip() for value in configured if str(value).strip()]
    if len(projects) >= 2:
        return list(dict.fromkeys(projects))
    parts = re.split(r"\s+(?:versus|vs\.?|compared\s+to)\s+", topic, flags=re.IGNORECASE)
    if len(parts) < 2:
        return []
    trailing_context = re.compile(
        r"\s+(?:inference\s+engines?|frameworks?|projects?|repositories|comparison)\s*$",
        flags=re.IGNORECASE,
    )
    normalized = [trailing_context.sub("", part).strip(" ,:;-") for part in parts]
    return list(dict.fromkeys(project for project in normalized if project))


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "facet"
