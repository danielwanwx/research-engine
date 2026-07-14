"""Research Engine runner."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import re
from typing import Any, Callable

from research_engine.artifacts import render_report, slugify, write_json, write_jsonl
from research_engine.connectors import (
    AgentReachBridgeConnector,
    ExternalJsonlConnector,
    FinanceQuoteConnector,
    GitHubPublicSearchConnector,
    ManualConnector,
    OfficialJobDiscoveryConnector,
    OpenCliBridgeConnector,
    WebPageConnector,
    XaiDiscoveryConnector,
)
from research_engine.execution import ConnectorExecutionOptions, execute_collection_requests
from research_engine.loop import build_loop_contract, build_loop_record
from research_engine.models import CollectionRequest, CollectionResult, ResearchRunResult, utc_now
from research_engine.packs import build_pack_queries, pack_summary, select_research_pack
from research_engine.platforms import build_platform_research_plan
from research_engine.quality import enrich_rows_with_quality
from research_engine.security import (
    artifact_path_ref,
    redact_text,
    sanitize_for_artifact,
    sensitive_paths,
    sensitive_value_paths,
)
from research_engine.synthesis import (
    build_claim_review,
    build_decision_brief,
    build_supply_demand_matrix,
)
from research_engine.targets import (
    ATS_HOSTS,
    COMMUNITY_HOSTS,
    COMPANY_DOMAINS,
    EXPERT_HOSTS,
    ResearchTarget,
    build_target_claim_review,
    classify_target_evidence,
)
from urllib.parse import urlsplit


ConnectorProvider = Any | Callable[[], Any]

DEFAULT_CONNECTORS: dict[str, ConnectorProvider] = {
    AgentReachBridgeConnector.connector_id: AgentReachBridgeConnector,
    ExternalJsonlConnector.connector_id: ExternalJsonlConnector,
    FinanceQuoteConnector.connector_id: FinanceQuoteConnector,
    GitHubPublicSearchConnector.connector_id: GitHubPublicSearchConnector,
    ManualConnector.connector_id: ManualConnector,
    OfficialJobDiscoveryConnector.connector_id: OfficialJobDiscoveryConnector,
    OpenCliBridgeConnector.connector_id: OpenCliBridgeConnector,
    WebPageConnector.connector_id: WebPageConnector,
    XaiDiscoveryConnector.connector_id: XaiDiscoveryConnector,
}

DEPTH_MAX_RESULTS = {"quick": 3, "deep": 8, "audit": 12}


class ResearchEngine:
    def __init__(
        self,
        *,
        pack_dir: Path | None = None,
        output_dir: Path | None = None,
        connectors: dict[str, ConnectorProvider] | None = None,
        max_workers: int = 4,
        retries: int = 1,
        cache_dir: Path | None = None,
        source_timeout_seconds: float | None = None,
    ) -> None:
        self.pack_dir = pack_dir
        self.output_dir = output_dir or Path("runs")
        self.connector_factories = {**DEFAULT_CONNECTORS, **(connectors or {})}
        self.execution_options = ConnectorExecutionOptions(
            max_workers=max_workers,
            retries=retries,
            cache_dir=cache_dir,
            source_timeout_seconds=source_timeout_seconds,
        )

    def run(
        self,
        topic: str,
        *,
        depth: str = "quick",
        dry_run: bool = False,
        pack_id: str | None = None,
        run_date: str | None = None,
        slug: str | None = None,
        external_evidence_paths: list[Path] | None = None,
        platform_scope: str = "broad",
        web_search_pages: bool = False,
        target: ResearchTarget | dict[str, Any] | None = None,
        agent_reach: bool = False,
        agent_reach_command_templates: list[str] | None = None,
    ) -> ResearchRunResult:
        if depth not in DEPTH_MAX_RESULTS:
            supported = ", ".join(sorted(DEPTH_MAX_RESULTS))
            raise ValueError(f"unsupported depth: {depth}; supported: {supported}")
        resolved_target = ResearchTarget.from_mapping(target) if target is not None else None
        selected_pack = select_research_pack(topic, pack_dir=self.pack_dir, pack_id=pack_id)
        resolved_date = run_date or date.today().isoformat()
        run_id = f"{resolved_date}-{slug or slugify(topic)}"
        run_dir = self.output_dir / run_id
        max_results = DEPTH_MAX_RESULTS[depth]
        platform_plan = build_platform_research_plan(
            topic,
            scope=platform_scope,
            pack=selected_pack,
        )
        source_requests = build_source_requests(
            selected_pack,
            topic=topic,
            external_evidence_paths=external_evidence_paths,
            platform_plan=platform_plan,
            github_public=platform_scope == "all",
            web_search_pages=web_search_pages,
            target=resolved_target,
            agent_reach=agent_reach,
            agent_reach_command_templates=agent_reach_command_templates,
        )
        query_plan = {
            "topic": topic,
            "artifact_contract": "target_intelligence.v1" if resolved_target else "research_engine.v1",
            "target": resolved_target.as_dict() if resolved_target else None,
            "pack": pack_summary(selected_pack),
            "depth": depth,
            "max_results_per_source": max_results,
            "platform_scope": platform_scope,
            "platform_research_plan": platform_plan,
            "queries": build_pack_queries(topic, selected_pack),
            "collection_modes": {
                "structured_target": resolved_target is not None,
                "official_job_discovery": any(
                    request.source.get("connector") == "official_job_discovery"
                    for request in source_requests
                ),
                "xai_discovery": any(
                    request.source.get("connector") == "xai_discovery"
                    for request in source_requests
                ),
                "external_evidence": bool(external_evidence_paths),
                "agent_reach": agent_reach,
                "opencli": any(
                    request.source.get("connector") == "opencli_bridge"
                    for request in source_requests
                ),
                "github_public": any(
                    request.source.get("connector") == "github_public_search"
                    for request in source_requests
                ),
                "web_search_pages": any(
                    request.source.get("source_kind") == "platform_search_page"
                    for request in source_requests
                ),
            },
            "agent_reach_commands": [
                redact_text(template) for template in agent_reach_command_templates or []
            ],
            "external_evidence_paths": [
                artifact_path_ref(path) for path in external_evidence_paths or []
            ],
            "sources": [
                {
                    "source_id": request.source_id,
                    "connector": request.source.get("connector"),
                }
                for request in source_requests
            ]
            + (
                [
                    {
                        "source_id": "target_discovery_refetch",
                        "connector": "web_page",
                        "conditional": True,
                    }
                ]
                if resolved_target
                else []
            ),
        }
        loop_contract = build_loop_contract(
            topic=topic,
            pack=selected_pack,
            query_plan=query_plan,
            dry_run=dry_run,
            execution_options={
                "max_workers": self.execution_options.max_workers,
                "retries": self.execution_options.retries,
                "cache_enabled": self.execution_options.cache_dir is not None,
                "source_timeout_seconds": self.execution_options.source_timeout_seconds,
            },
        )
        collection_results: list[CollectionResult] = []
        warnings: list[str] = []
        execution_report = {
            "generated_at": utc_now(),
            "max_workers": self.execution_options.max_workers,
            "retries": self.execution_options.retries,
            "cache_enabled": self.execution_options.cache_dir is not None,
            "source_timeout_seconds": self.execution_options.source_timeout_seconds,
            "request_count": 0,
            "status_counts": {},
            "requests": [],
        }
        if not dry_run and not source_requests:
            warnings.append(f"research pack {selected_pack.get('id')} has no executable sources")
        if not dry_run:
            executable_requests = [
                CollectionRequest(
                    source=source.source,
                    topic=topic,
                    run_date=resolved_date,
                    depth=depth,
                    max_results=max_results,
                )
                for source in source_requests
            ]
            collection_results, execution_warnings, execution_report = execute_collection_requests(
                executable_requests,
                connector_providers=self.connector_factories,
                options=self.execution_options,
            )
            warnings.extend(execution_warnings)
            if resolved_target:
                discovery_rows = normalize_rows(collection_results)
                refetch_request = build_target_refetch_request(
                    discovery_rows,
                    target=resolved_target,
                    topic=topic,
                    run_date=resolved_date,
                    depth=depth,
                    max_results=max_results,
                )
                if refetch_request:
                    refetch_results, refetch_warnings, refetch_report = execute_collection_requests(
                        [refetch_request],
                        connector_providers=self.connector_factories,
                        options=self.execution_options,
                    )
                    collection_results.extend(refetch_results)
                    warnings.extend(refetch_warnings)
                    execution_report = merge_execution_reports(execution_report, refetch_report)
        rows = normalize_rows(collection_results)
        rows, sanitation_warnings = sanitize_rows_for_artifacts(rows)
        warnings.extend(sanitation_warnings)
        if resolved_target:
            rows = classify_target_evidence(rows, target=resolved_target, run_date=resolved_date)
        rows, quality_report = enrich_rows_with_quality(rows, topic=topic, pack=selected_pack)
        if resolved_target:
            rows = classify_target_evidence(rows, target=resolved_target, run_date=resolved_date)
            claim_review = build_target_claim_review(
                resolved_target,
                rows,
                warnings=[*warnings, *quality_report.get("warnings", [])],
                run_date=resolved_date,
            )
            quality_report["target_fitness_summary"] = target_fitness_summary(rows)
        else:
            claim_review = build_claim_review(
                topic=topic,
                pack=selected_pack,
                rows=rows,
                warnings=[*warnings, *quality_report.get("warnings", [])],
            )
        matrix = build_supply_demand_matrix(topic=topic, pack=selected_pack, rows=rows)
        decision_brief = build_decision_brief(
            topic=topic,
            pack=selected_pack,
            claim_review=claim_review,
            matrix=matrix,
        )
        status = run_status(
            dry_run=dry_run, rows=rows, warnings=warnings, source_requests=source_requests
        )
        loop_record = build_loop_record(
            topic=topic,
            status=status,
            dry_run=dry_run,
            rows=rows,
            warnings=warnings,
            query_plan=query_plan,
            execution_report=execution_report,
            quality_report=quality_report,
            claim_review=claim_review,
            decision_brief=decision_brief,
        )
        manifest = {
            "run_id": run_id,
            "topic": topic,
            "created_at": utc_now(),
            "implementation_path": str(Path(__file__).resolve().parents[2]),
            "status": status,
            "artifact_contract": "target_intelligence.v1" if resolved_target else "research_engine.v1",
            "target": resolved_target.as_dict() if resolved_target else None,
            "target_outcome": dict(claim_review.get("overall") or {}) if resolved_target else None,
            "pack": pack_summary(selected_pack),
            "warnings": warnings,
            "execution_summary": {
                "request_count": execution_report.get("request_count", 0),
                "status_counts": execution_report.get("status_counts") or {},
                "cache_enabled": bool(execution_report.get("cache_enabled")),
            },
            "quality_summary": {
                "average_quality_score": quality_report.get("average_quality_score"),
                "duplicate_cluster_count": quality_report.get("duplicate_cluster_count"),
                "conflict_flag_count": len(quality_report.get("conflict_flags") or []),
            },
            "loop_summary": {
                "loop_status": loop_record.get("loop_status"),
                "stop_reason": loop_record.get("stop_reason"),
                "feedback_action_count": len(loop_record.get("feedback_actions") or []),
            },
        }
        write_json(run_dir / "run_manifest.json", manifest)
        write_json(run_dir / "query_plan.json", query_plan)
        write_json(run_dir / "collection_execution.json", execution_report)
        write_jsonl(run_dir / "evidence.jsonl", rows)
        write_json(run_dir / "evidence_quality.json", quality_report)
        write_json(run_dir / "claim_review.json", claim_review)
        write_json(run_dir / "supply_demand_matrix.json", matrix)
        write_json(run_dir / "decision_brief.json", decision_brief)
        write_json(run_dir / "loop_contract.json", loop_contract)
        write_json(run_dir / "loop_record.json", loop_record)
        (run_dir / "research_report.md").write_text(
            render_report(
                topic=topic,
                pack_id=str(selected_pack.get("id")),
                raw_rows=rows,
                claim_review=claim_review,
                decision_brief=decision_brief,
                quality_report=quality_report,
                loop_record=loop_record,
            ),
            encoding="utf-8",
        )
        return ResearchRunResult(
            run_id=run_id,
            run_dir=str(run_dir),
            topic=topic,
            pack_id=str(selected_pack.get("id") or "generic"),
            status=status,
            dry_run=dry_run,
            raw_rows=len(rows),
            loop_status=str(loop_record.get("loop_status") or ""),
            stop_reason=str(loop_record.get("stop_reason") or ""),
            feedback_action_count=len(loop_record.get("feedback_actions") or []),
            warnings=warnings,
        )


def run_research(topic: str, **kwargs: Any) -> ResearchRunResult:
    return ResearchEngine(**kwargs.pop("engine_kwargs", {})).run(topic, **kwargs)


def build_source_requests(
    pack: dict[str, Any],
    *,
    topic: str,
    external_evidence_paths: list[Path] | None = None,
    platform_plan: list[dict[str, Any]] | None = None,
    github_public: bool = False,
    web_search_pages: bool = False,
    target: ResearchTarget | None = None,
    agent_reach: bool = False,
    agent_reach_command_templates: list[str] | None = None,
) -> list[CollectionRequest]:
    sources: list[dict[str, Any]] = []
    if target:
        sources.extend(
            [
                {
                    "source_id": "official_job_discovery",
                    "connector": "official_job_discovery",
                    "target": target.as_dict(),
                    "source_kind": "official_target_discovery",
                    "access_mode": "public_official_endpoints",
                },
                {
                    "source_id": "xai_target_discovery",
                    "connector": "xai_discovery",
                    "target": target.as_dict(),
                    "timeout_seconds": 75.0,
                    "source_kind": "dynamic_public_discovery",
                    "access_mode": "xai_web_and_x_search",
                },
            ]
        )
    else:
        for source in pack.get("sources") or []:
            if isinstance(source, dict):
                sources.append(dict(source))
    if pack.get("finance_tickers"):
        sources.append(
            {
                "source_id": "finance_quote_watchlist",
                "connector": "finance_quote",
                "tickers": pack.get("finance_tickers") or [],
            }
        )
    if pack.get("web_pages"):
        sources.append(
            {
                "source_id": "web_seed_pages",
                "connector": "web_page",
                "pages": pack.get("web_pages") or [],
            }
        )
    github_query = github_query_from_platform_plan(platform_plan or []) if github_public else ""
    if github_public and github_query:
        sources.append(
            {
                "source_id": "github_public_search",
                "connector": "github_public_search",
                "platform": "github",
                "query": github_query,
                "source_kind": "github_public_repository",
                "access_mode": "public_github_api",
            }
        )
    if web_search_pages:
        pages = platform_search_pages(platform_plan or [])
        if pages:
            sources.append(
                {
                    "source_id": "platform_search_pages",
                    "connector": "web_page",
                    "pages": pages,
                    "source_kind": "platform_search_page",
                    "access_mode": "public_search_page_fetch",
                }
            )
    if external_evidence_paths:
        sources.append(
            {
                "source_id": "external_evidence_jsonl",
                "connector": "external_jsonl",
                "paths": [str(path) for path in external_evidence_paths],
                "source_kind": "external_logged_in_evidence",
                "access_mode": "external_authorized_capture",
            }
        )
    if agent_reach:
        sources.append(
            build_agent_reach_bridge_source(
                topic=topic,
                platform_plan=platform_plan or [],
                command_templates=agent_reach_command_templates,
            )
        )
    return [
        CollectionRequest(
            source=source,
            topic=topic,
            run_date="",
            depth="quick",
            max_results=DEPTH_MAX_RESULTS["quick"],
        )
        for source in sources
    ]


def platform_search_pages(platform_plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert public platform search URLs into bounded web_page seed pages."""
    public_platforms = {"hackernews", "reddit", "github", "youtube"}
    pages: list[dict[str, Any]] = []
    for row in platform_plan:
        platform = str(row.get("platform") or "")
        url = str(row.get("search_url") or "")
        if not platform or platform not in public_platforms or not url:
            continue
        if bool(row.get("requires_login")):
            continue
        pages.append(
            {
                "url": url,
                "title": f"{row.get('label') or platform} search",
                "publisher": str(row.get("label") or platform),
                "source_confidence": "medium",
            }
        )
    return pages[:6]


def build_agent_reach_bridge_source(
    *,
    topic: str,
    platform_plan: list[dict[str, Any]],
    command_templates: list[str] | None,
) -> dict[str, Any]:
    platform_queries = {
        str(row.get("platform")): str(row.get("query") or topic)
        for row in platform_plan
        if row.get("platform")
    }
    if not platform_queries:
        platform_queries = {platform: topic for platform in ("x", "reddit", "github", "youtube")}
    return {
        "source_id": "agent_reach_bridge",
        "connector": "agent_reach_bridge",
        "query_strategy": {
            "query": topic,
            "platforms": list(platform_queries),
            "platform_queries": platform_queries,
            "command_templates": list(command_templates or []),
        },
        "source_kind": "agent_reach_bridge",
        "access_mode": "agent_reach_or_upstream_cli",
    }


def github_query_from_platform_plan(platform_plan: list[dict[str, Any]]) -> str:
    for row in platform_plan:
        if row.get("platform") == "github":
            return str(row.get("query") or "")
    return ""


def build_target_refetch_request(
    rows: list[dict[str, Any]],
    *,
    target: ResearchTarget,
    topic: str,
    run_date: str,
    depth: str,
    max_results: int,
) -> CollectionRequest | None:
    pages: list[dict[str, Any]] = []
    for row in rows:
        if row.get("connector") != "xai_discovery":
            continue
        url = str(row.get("url") or "")
        if not url:
            continue
        source_kind, company = discovery_candidate_kind(url, target=target)
        page = {
            "url": url,
            "title": str(row.get("title") or url),
            "publisher": str(row.get("publisher") or urlsplit(url).netloc),
            "source_confidence": "medium",
            "source_kind": source_kind,
            "access_mode": "public_discovery_refetch",
            "discovered_via": str(row.get("discovered_via") or "xai_search"),
            "discovery_source_id": str(row.get("source_id") or ""),
        }
        if company:
            page["company"] = company
        published_at = x_post_date(url)
        if published_at:
            page["published_at"] = published_at
        pages.append(page)
    if not pages:
        return None
    return CollectionRequest(
        source={
            "source_id": "target_discovery_refetch",
            "connector": "web_page",
            "pages": pages[:max_results],
            "target": target.as_dict(),
            "source_kind": "target_discovery_refetch",
            "access_mode": "public_url_refetch",
        },
        topic=topic,
        run_date=run_date,
        depth=depth,
        max_results=max_results,
    )


def discovery_candidate_kind(url: str, *, target: ResearchTarget) -> tuple[str, str]:
    parsed = urlsplit(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.lower()
    target_domains = COMPANY_DOMAINS.get(
        "".join(character for character in target.company.lower() if character.isalnum()), ()
    )
    target_official = any(host == domain or host.endswith("." + domain) for domain in target_domains)
    job_path = any(token in path for token in ("/job/", "/jobs/", "/listing/", "/positions/"))
    if (target_official or host in ATS_HOSTS) and job_path:
        return "official_job_posting", target.company
    if target_official:
        return "official_company_material", target.company
    if host in COMMUNITY_HOSTS:
        return "candidate_report", ""
    if host in EXPERT_HOSTS:
        return "expert_guide", ""
    return "generic_resource", ""


def x_post_date(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.netloc.lower().removeprefix("www.") not in {"x.com", "twitter.com"}:
        return ""
    match = re.search(r"/status/(\d+)", parsed.path)
    if not match:
        return ""
    try:
        timestamp_ms = (int(match.group(1)) >> 22) + 1288834974657
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return ""


def merge_execution_reports(*reports: dict[str, Any]) -> dict[str, Any]:
    base = dict(reports[0]) if reports else {}
    requests = [request for report in reports for request in report.get("requests") or []]
    status_counts: dict[str, int] = {}
    for request in requests:
        status = str(request.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    base.update(
        {
            "generated_at": utc_now(),
            "request_count": len(requests),
            "status_counts": status_counts,
            "requests": requests,
        }
    )
    return base


def target_fitness_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    dispositions: dict[str, int] = {}
    reasons: dict[str, int] = {}
    for row in rows:
        fitness = row.get("claim_fitness") or {}
        disposition = str(fitness.get("disposition") or "unknown")
        dispositions[disposition] = dispositions.get(disposition, 0) + 1
        for reason in fitness.get("rejection_reasons") or []:
            reason = str(reason)
            reasons[reason] = reasons.get(reason, 0) + 1
    return {"disposition_counts": dispositions, "rejection_reason_counts": reasons}


def normalize_rows(results: list[CollectionResult]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        for row in result.rows:
            normalized = dict(row)
            normalized.setdefault("source_id", result.source_id)
            normalized.setdefault("connector", result.connector)
            normalized.setdefault("url", normalized.get("source_url") or "")
            normalized["evidence_id"] = normalized.get("evidence_id") or f"ev-{len(rows) + 1:04d}"
            rows.append(normalized)
    return rows


def sanitize_rows_for_artifacts(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    sanitized_rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, row in enumerate(rows, start=1):
        sensitive = sorted({*sensitive_paths(row), *sensitive_value_paths(row)})
        safe_row = sanitize_for_artifact(row)
        if not isinstance(safe_row, dict):
            safe_row = {}
        if sensitive:
            row_label = str(
                safe_row.get("evidence_id")
                or safe_row.get("source_id")
                or safe_row.get("title")
                or f"row_{index}"
            )
            warnings.append(
                "artifact sanitation redacted/dropped sensitive field(s) in "
                f"{row_label}: {','.join(sensitive[:8])}"
            )
        sanitized_rows.append(safe_row)
    return sanitized_rows, warnings


def run_status(
    *,
    dry_run: bool,
    rows: list[dict[str, Any]],
    warnings: list[str],
    source_requests: list[CollectionRequest],
) -> str:
    if dry_run:
        return "planned"
    if not source_requests:
        return "failed_no_sources"
    if rows:
        return "complete_with_warnings" if warnings else "complete"
    return "failed_no_rows"
