"""Research Engine runner."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import re
from typing import Any, Callable
from urllib.parse import urlsplit

from research_engine.artifacts import render_report, slugify, write_json, write_jsonl
from research_engine.conflicts import build_independence_key
from research_engine.connectors import (
    AgentReachBridgeConnector,
    AnySearchConnector,
    ExternalJsonlConnector,
    FinanceQuoteConnector,
    GitHubPublicSearchConnector,
    ManualConnector,
    OfficialJobDiscoveryConnector,
    OpenCliBridgeConnector,
    WebPageConnector,
    WebSearchConnector,
    XaiDiscoveryConnector,
)
from research_engine.execution import ConnectorExecutionOptions, execute_collection_requests
from research_engine.extraction import build_chunks
from research_engine.freshness import enrich_row_freshness
from research_engine.job_market import build_job_market_snapshot
from research_engine.loop import build_loop_contract, build_loop_record
from research_engine.models import CollectionRequest, CollectionResult, ResearchRunResult, utc_now
from research_engine.packs import pack_summary, select_research_pack
from research_engine.pdf_report import render_pdf_report
from research_engine.planning import build_query_plan, collection_requests_from_plan
from research_engine.platforms import build_platform_research_plan
from research_engine.quality import canonicalize_url, enrich_rows_with_quality
from research_engine.repair import build_repair_plan, progress_fingerprint
from research_engine.security import (
    artifact_path_ref,
    redact_text,
    sanitize_for_artifact,
    sensitive_paths,
    sensitive_value_paths,
)
from research_engine.synthesis import (
    assign_claim_polarities,
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
ConnectorProvider = Any | Callable[[], Any]

DEFAULT_CONNECTORS: dict[str, ConnectorProvider] = {
    AgentReachBridgeConnector.connector_id: AgentReachBridgeConnector,
    AnySearchConnector.connector_id: AnySearchConnector,
    ExternalJsonlConnector.connector_id: ExternalJsonlConnector,
    FinanceQuoteConnector.connector_id: FinanceQuoteConnector,
    GitHubPublicSearchConnector.connector_id: GitHubPublicSearchConnector,
    ManualConnector.connector_id: ManualConnector,
    OfficialJobDiscoveryConnector.connector_id: OfficialJobDiscoveryConnector,
    OpenCliBridgeConnector.connector_id: OpenCliBridgeConnector,
    WebPageConnector.connector_id: WebPageConnector,
    WebSearchConnector.connector_id: WebSearchConnector,
    XaiDiscoveryConnector.connector_id: XaiDiscoveryConnector,
}

DEPTH_MAX_RESULTS = {"quick": 3, "deep": 8, "audit": 12}
TARGET_DISCOVERY_CACHE_TTL_SECONDS = 86_400


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
        overall_deadline_seconds: float | None = None,
        host_max_concurrency: int = 2,
        host_delay_seconds: float = 0.1,
    ) -> None:
        self.pack_dir = pack_dir
        self.output_dir = output_dir or Path("runs")
        self.connector_factories = {**DEFAULT_CONNECTORS, **(connectors or {})}
        self.execution_options = ConnectorExecutionOptions(
            max_workers=max_workers,
            retries=retries,
            cache_dir=cache_dir,
            source_timeout_seconds=source_timeout_seconds,
            overall_deadline_seconds=overall_deadline_seconds,
            host_max_concurrency=host_max_concurrency,
            host_delay_seconds=host_delay_seconds,
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
        research_scope: dict[str, Any] | None = None,
        search_provider: str = "none",
        search_endpoint: str = "",
        as_of: str | None = None,
    ) -> ResearchRunResult:
        if depth not in DEPTH_MAX_RESULTS:
            supported = ", ".join(sorted(DEPTH_MAX_RESULTS))
            raise ValueError(f"unsupported depth: {depth}; supported: {supported}")
        resolved_target = ResearchTarget.from_mapping(target) if target is not None else None
        selected_pack = select_research_pack(topic, pack_dir=self.pack_dir, pack_id=pack_id)
        resolved_date = run_date or date.today().isoformat()
        m2_plan = build_query_plan(
            topic,
            pack=selected_pack,
            depth=depth,
            scope=research_scope,
            search_provider=search_provider,
            search_endpoint=search_endpoint,
        )
        resolved_as_of = str(as_of or (m2_plan.get("scope") or {}).get("as_of") or resolved_date)
        try:
            date.fromisoformat(resolved_as_of)
        except ValueError as exc:
            raise ValueError("as_of must be YYYY-MM-DD") from exc
        requested_run_id = f"{resolved_date}-{slug or slugify(topic)}"
        run_id, run_dir = reserve_run_dir(self.output_dir, requested_run_id)
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
        if not resolved_target:
            planned_requests = collection_requests_from_plan(
                m2_plan,
                topic=topic,
                run_date=resolved_date,
            )
            planned_requests = expand_job_market_requests(
                planned_requests,
                scope=m2_plan.get("scope"),
                depth=depth,
            )
            for request in planned_requests:
                if request.source.get("connector") == "web_search" and search_endpoint:
                    request.source["endpoint"] = search_endpoint
            source_requests.extend(
                request
                for request in planned_requests
                if not (
                    request.source.get("connector") == "web_search"
                    and search_provider in {"", "none"}
                )
            )
        query_plan = {
            **m2_plan,
            "topic": topic,
            "artifact_contract": "target_intelligence.v1" if resolved_target else "research_engine.v2",
            "target": resolved_target.as_dict() if resolved_target else None,
            "pack": pack_summary(selected_pack),
            "depth": depth,
            "as_of": resolved_as_of,
            "max_results_per_source": max_results,
            "platform_scope": platform_scope,
            "platform_research_plan": platform_plan,
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
                "web_search": any(
                    request.source.get("connector") == "web_search"
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
                        "query_id": request.source.get("query_id"),
                        "facet_id": request.source.get("facet_id"),
                        "pass_id": request.source.get("pass_id") or "pass-1",
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
                "overall_deadline_seconds": self.execution_options.overall_deadline_seconds,
                "host_max_concurrency": self.execution_options.host_max_concurrency,
                "host_delay_seconds": self.execution_options.host_delay_seconds,
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
            "overall_deadline_seconds": self.execution_options.overall_deadline_seconds,
            "host_max_concurrency": self.execution_options.host_max_concurrency,
            "host_delay_seconds": self.execution_options.host_delay_seconds,
            "request_count": 0,
            "status_counts": {},
            "requests": [],
        }
        repair_record: dict[str, Any] = {
            "schema_version": "repair_record.v1",
            "attempted": False,
            "pass_id": "",
            "trigger_count": 0,
            "failures": [],
            "facets": [],
            "before_progress_fingerprint": "",
            "after_progress_fingerprint": "",
            "stop_reason": "dry_run" if dry_run else "not_required",
        }
        if not dry_run and not source_requests:
            warnings.append(f"research pack {selected_pack.get('id')} has no executable sources")
        if not dry_run:
            executable_requests = [
                CollectionRequest(
                    source=source.source,
                    topic=topic,
                    run_date=resolved_date,
                    depth=source.depth or depth,
                    max_results=source.max_results or max_results,
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
            elif not resolved_target:
                canonical_request = build_canonical_refetch_request(
                    collection_results,
                    topic=topic,
                    run_date=resolved_date,
                    depth=depth,
                    max_results=int((m2_plan.get("budget") or {}).get("max_canonical_refetches") or 0),
                )
                if canonical_request:
                    refetch_results, refetch_warnings, refetch_report = execute_collection_requests(
                        [canonical_request],
                        connector_providers=self.connector_factories,
                        options=self.execution_options,
                    )
                    collection_results.extend(refetch_results)
                    warnings.extend(refetch_warnings)
                    execution_report = merge_execution_reports(execution_report, refetch_report)
            if not resolved_target:
                interim_rows = normalize_rows(collection_results)
                interim_rows = enrich_rows_with_freshness(
                    interim_rows,
                    query_plan=query_plan,
                    as_of=resolved_as_of,
                )
                interim_rows, interim_quality = enrich_rows_with_quality(
                    interim_rows,
                    topic=topic,
                    pack=selected_pack,
                    query_plan=query_plan,
                )
                failures = build_repair_failures(
                    query_plan=query_plan,
                    rows=interim_rows,
                    execution_report=execution_report,
                    quality_report=interim_quality,
                )
                before_fingerprint = progress_fingerprint(interim_rows, failures)
                repair_plan = build_repair_plan(
                    list(query_plan.get("queries") or []),
                    failures,
                    as_of=resolved_as_of,
                    search_enabled=search_provider not in {"", "none"},
                    current_progress_fingerprint=before_fingerprint,
                    max_refetch_candidates=max_results,
                )
                repair_record.update(
                    {
                        "failures": failures,
                        "facets": list(repair_plan.get("facets") or []),
                        "trigger_count": int(repair_plan.get("trigger_count") or 0),
                        "before_progress_fingerprint": before_fingerprint,
                        "stop_reason": str(repair_plan.get("stop_reason") or "not_required"),
                    }
                )
                if repair_plan.get("should_repair"):
                    repair_requests = build_repair_requests(
                        m2_plan,
                        repair_plan=repair_plan,
                        topic=topic,
                        run_date=resolved_date,
                    )
                    repair_results, repair_warnings, repair_execution = (
                        execute_collection_requests(
                            repair_requests,
                            connector_providers=self.connector_factories,
                            options=self.execution_options,
                        )
                    )
                    collection_results.extend(repair_results)
                    warnings.extend(repair_warnings)
                    execution_report = merge_execution_reports(
                        execution_report,
                        repair_execution,
                    )
                    repair_refetch = build_canonical_refetch_request(
                        repair_results,
                        topic=topic,
                        run_date=resolved_date,
                        depth=depth,
                        max_results=max_results,
                        source_id="canonical_refetch_pass_2",
                        pass_id="pass-2-canonical-refetch",
                    )
                    if repair_refetch:
                        repaired_pages, refetch_warnings, refetch_execution = (
                            execute_collection_requests(
                                [repair_refetch],
                                connector_providers=self.connector_factories,
                                options=self.execution_options,
                            )
                        )
                        collection_results.extend(repaired_pages)
                        warnings.extend(refetch_warnings)
                        execution_report = merge_execution_reports(
                            execution_report,
                            refetch_execution,
                        )
                    final_probe_rows = normalize_rows(collection_results)
                    final_probe_rows = enrich_rows_with_freshness(
                        final_probe_rows,
                        query_plan=query_plan,
                        as_of=resolved_as_of,
                    )
                    final_probe_rows, final_probe_quality = enrich_rows_with_quality(
                        final_probe_rows,
                        topic=topic,
                        pack=selected_pack,
                        query_plan=query_plan,
                    )
                    final_failures = build_repair_failures(
                        query_plan=query_plan,
                        rows=final_probe_rows,
                        execution_report=execution_report,
                        quality_report=final_probe_quality,
                    )
                    after_fingerprint = progress_fingerprint(final_probe_rows, final_failures)
                    repair_record.update(
                        {
                            "attempted": True,
                            "pass_id": "pass-2",
                            "after_progress_fingerprint": after_fingerprint,
                            "stop_reason": (
                                "repair_no_progress"
                                if after_fingerprint == before_fingerprint
                                else "repair_completed"
                            ),
                        }
                    )
        reconcile_query_plan(query_plan, execution_report)
        rows = normalize_rows(collection_results)
        rows, sanitation_warnings = sanitize_rows_for_artifacts(rows)
        warnings.extend(sanitation_warnings)
        rows = enrich_rows_with_freshness(
            rows,
            query_plan=query_plan,
            as_of=resolved_as_of,
        )
        chunks = build_evidence_chunks(rows)
        analysis_rows = rows
        if resolved_target:
            rows = classify_target_evidence(rows, target=resolved_target, run_date=resolved_date)
            rows, quality_report = enrich_rows_with_quality(
                rows,
                topic=topic,
                pack=selected_pack,
                query_plan=query_plan,
            )
        else:
            rows = assign_claim_polarities(
                rows,
                specs=[
                    spec
                    for spec in selected_pack.get("claim_specs") or []
                    if isinstance(spec, dict)
                ],
            )
            rows, _parent_quality_report = enrich_rows_with_quality(
                rows,
                topic=topic,
                pack=selected_pack,
                query_plan=query_plan,
            )
            analysis_rows = assign_claim_polarities(
                build_analysis_rows(rows, chunks),
                specs=[
                    spec
                    for spec in selected_pack.get("claim_specs") or []
                    if isinstance(spec, dict)
                ],
            )
            analysis_rows, quality_report = enrich_rows_with_quality(
                analysis_rows,
                topic=topic,
                pack=selected_pack,
                query_plan=query_plan,
            )
            chunks = [row for row in analysis_rows if row.get("is_chunk")]
        if resolved_target:
            rows = classify_target_evidence(rows, target=resolved_target, run_date=resolved_date)
            analysis_rows = rows
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
                rows=analysis_rows,
                warnings=[*warnings, *quality_report.get("warnings", [])],
                conflict_flags=quality_report.get("conflict_flags") or [],
            )
            if query_plan.get("profile") == "market_landscape":
                context = {
                    **dict(query_plan.get("claim_context") or {}),
                    "as_of": resolved_as_of,
                }
                claim_review["claim_context"] = context
                for claim in claim_review.get("claims") or []:
                    claim["claim_context"] = context
        job_market_snapshot: dict[str, Any] | None = None
        if query_plan.get("profile") == "job_market" and m2_plan.get("scope"):
            job_market_snapshot = build_job_market_snapshot_from_run(
                rows,
                scope={**dict(m2_plan["scope"]), "as_of": resolved_as_of},
                execution_report=execution_report,
                unsupported_sources=list(
                    (query_plan.get("job_company_coverage") or {}).get(
                        "unsupported_by_depth_budget"
                    )
                    or []
                ),
            )
        matrix = build_supply_demand_matrix(
            topic=topic,
            pack=selected_pack,
            rows=analysis_rows,
        )
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
            repair_record=repair_record,
            facet_coverage=dict(quality_report.get("facet_coverage") or {}),
        )
        cost_record = build_cost_record(
            execution_report,
            paid_discovery=paid_discovery,
            paid_call_budget=paid_call_budget,
        )
        manifest = {
            "run_id": run_id,
            "topic": topic,
            "created_at": utc_now(),
            "implementation_path": str(Path(__file__).resolve().parents[2]),
            "status": status,
            "artifact_contract": "target_intelligence.v1" if resolved_target else "research_engine.v2",
            "profile": str(query_plan.get("profile") or "generic"),
            "as_of": resolved_as_of,
            "search_provider": search_provider,
            "target": resolved_target.as_dict() if resolved_target else None,
            "target_outcome": dict(claim_review.get("overall") or {}) if resolved_target else None,
            "pack": pack_summary(selected_pack),
            "warnings": warnings,
            "execution_summary": {
                "request_count": execution_report.get("request_count", 0),
                "status_counts": execution_report.get("status_counts") or {},
                "cache_enabled": bool(execution_report.get("cache_enabled")),
                "paid_calls_attempted": cost_record["paid_calls_attempted"],
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
        write_json(run_dir / "repair_record.json", repair_record)
        write_jsonl(run_dir / "evidence.jsonl", rows)
        write_jsonl(run_dir / "chunks.jsonl", chunks)
        write_json(run_dir / "evidence_quality.json", quality_report)
        write_json(
            run_dir / "facet_coverage.json",
            dict(quality_report.get("facet_coverage") or {}),
        )
        write_json(run_dir / "claim_review.json", claim_review)
        if job_market_snapshot is not None:
            write_json(run_dir / "job_market_snapshot.json", job_market_snapshot)
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
                status=status,
                profile=str(query_plan.get("profile") or "generic"),
                as_of=resolved_as_of,
                facet_coverage=dict(quality_report.get("facet_coverage") or {}),
                job_market_snapshot=job_market_snapshot,
            ),
            encoding="utf-8",
        )
        pdf_status = render_pdf_report(run_dir)
        pdf_status["error_message"] = redact_text(pdf_status.get("error_message") or "")
        write_json(run_dir / "pdf_report_status.json", pdf_status)
        if pdf_status.get("status") != "generated":
            warnings.append(
                "PDF report generation failed: "
                f"{pdf_status.get('error_type') or 'unknown_error'}"
            )
        manifest["warnings"] = warnings
        manifest["pdf_report"] = pdf_status
        write_json(run_dir / "run_manifest.json", manifest)
        pdf_report_path = (
            str(run_dir / str(pdf_status.get("path") or "research_report.pdf"))
            if pdf_status.get("status") == "generated"
            else ""
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
            pdf_report_path=pdf_report_path,
            pdf_report_status=str(pdf_status.get("status") or "failed"),
            warnings=warnings,
        )


def run_research(topic: str, **kwargs: Any) -> ResearchRunResult:
    return ResearchEngine(**kwargs.pop("engine_kwargs", {})).run(topic, **kwargs)


def reserve_run_dir(output_dir: Path, requested_run_id: str) -> tuple[str, Path]:
    """Atomically reserve a unique, human-readable run directory."""

    output_dir.mkdir(parents=True, exist_ok=True)
    sequence = 1
    while True:
        run_id = requested_run_id if sequence == 1 else f"{requested_run_id}--{sequence:02d}"
        run_dir = output_dir / run_id
        try:
            run_dir.mkdir(exist_ok=False)
        except FileExistsError:
            sequence += 1
            continue
        return run_id, run_dir


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


def build_canonical_refetch_request(
    results: list[CollectionResult],
    *,
    topic: str,
    run_date: str,
    depth: str,
    max_results: int,
    source_id: str = "canonical_refetch",
    pass_id: str = "canonical-refetch",
) -> CollectionRequest | None:
    """Turn discovery-only search results into a bounded canonical fetch pass."""

    if max_results <= 0:
        return None
    pages: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for result in results:
        if result.connector != "web_search":
            continue
        for index, row in enumerate(result.rows, start=1):
            url = str(row.get("url") or "").strip()
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc or url in seen_urls:
                continue
            seen_urls.add(url)
            discovery_source_id = str(
                row.get("discovery_source_id")
                or f"{result.source_id}:{row.get('query_id') or 'query'}:{index}"
            )
            row["discovery_source_id"] = discovery_source_id
            pages.append(
                {
                    "url": url,
                    "title": str(row.get("title") or url),
                    "publisher": str(row.get("publisher") or parsed.netloc),
                    "source_confidence": "medium",
                    "source_kind": "canonical_web_page",
                    "source_class": "canonical_content",
                    "access_mode": "public_discovery_refetch",
                    "discovered_via": str(row.get("discovered_via") or "web_search"),
                    "discovery_source_id": discovery_source_id,
                    "query_id": str(row.get("query_id") or ""),
                    "facet_id": str(row.get("facet_id") or ""),
                }
            )
            if len(pages) >= max_results:
                break
        if len(pages) >= max_results:
            break
    if not pages:
        return None
    return CollectionRequest(
        source={
            "source_id": source_id,
            "connector": "web_page",
            "pass_id": pass_id,
            "pages": pages,
            "source_kind": "canonical_web_page",
            "access_mode": "public_discovery_refetch",
        },
        topic=topic,
        run_date=run_date,
        depth=depth,
        max_results=len(pages),
    )


def build_repair_requests(
    base_plan: dict[str, Any],
    *,
    repair_plan: dict[str, Any],
    topic: str,
    run_date: str,
) -> list[CollectionRequest]:
    repair_facets = list(repair_plan.get("facets") or [])
    query_facets: list[dict[str, Any]] = []
    direct_refetches: list[CollectionRequest] = []
    for facet in repair_facets:
        reasons = set(facet.get("repair_reasons") or [facet.get("repair_reason")])
        candidate_urls = [str(url) for url in facet.get("candidate_urls") or [] if url]
        if "canonical_refetch_failure" in reasons and candidate_urls:
            direct_refetches.append(
                build_repair_refetch_request(
                    facet,
                    candidate_urls=candidate_urls,
                    topic=topic,
                    run_date=run_date,
                    depth=str(base_plan.get("depth") or "deep"),
                )
            )
        if reasons - {"canonical_refetch_failure"}:
            query_facets.append(facet)

    plan = {**base_plan, "queries": query_facets}
    requests = collection_requests_from_plan(plan, topic=topic, run_date=run_date)
    requests = [
        request
        for request in requests
        if not (
            request.source.get("connector") == "web_search"
            and plan.get("search_provider") in {"", "none"}
        )
    ]
    requests = expand_job_market_requests(
        requests,
        scope=base_plan.get("scope"),
        depth=str(base_plan.get("depth") or "deep"),
    )
    requests.extend(direct_refetches)
    for request in requests:
        request.source["source_id"] = f"repair-{request.source_id}"
        request.source["pass_id"] = "pass-2"
    return requests


def build_repair_refetch_request(
    facet: dict[str, Any],
    *,
    candidate_urls: list[str],
    topic: str,
    run_date: str,
    depth: str,
) -> CollectionRequest:
    """Build a direct pass-2 canonical fetch without repeating search."""

    query_id = str(facet.get("query_id") or "repair-query")
    facet_id = str(facet.get("facet_id") or "repair-facet")
    pages = [
        {
            "url": url,
            "title": url,
            "publisher": urlsplit(url).netloc,
            "source_confidence": "medium",
            "source_kind": "canonical_web_page",
            "source_class": "canonical_content",
            "access_mode": "public_repair_refetch",
            "discovered_via": "web_search",
            "discovery_source_id": f"repair:{query_id}:{index}",
            "query_id": query_id,
            "facet_id": facet_id,
        }
        for index, url in enumerate(candidate_urls, start=1)
    ]
    return CollectionRequest(
        source={
            "source_id": f"{query_id}-canonical-refetch",
            "connector": "web_page",
            "pass_id": "pass-2",
            "query_id": query_id,
            "facet_id": facet_id,
            "pages": pages,
            "source_kind": "canonical_web_page",
            "access_mode": "public_repair_refetch",
        },
        topic=topic,
        run_date=run_date,
        depth=depth,
        max_results=len(pages),
    )


def expand_job_market_requests(
    requests: list[CollectionRequest],
    *,
    scope: dict[str, Any] | None,
    depth: str,
) -> list[CollectionRequest]:
    """Expand one scoped job facet into a bounded request per requested company."""

    official = [
        request
        for request in requests
        if request.source.get("connector") == "official_job_discovery"
    ]
    if not official:
        return requests
    non_official = [
        request
        for request in requests
        if request.source.get("connector") != "official_job_discovery"
    ]
    if not scope or scope.get("profile") != "job_market":
        return non_official
    filters = scope.get("filters") or {}
    limits = {"quick": 5, "deep": 12, "audit": 20}
    companies = list(filters.get("companies") or [])[: limits.get(depth, 5)]
    role_title = str((filters.get("role_terms") or [""])[0])
    level = str((filters.get("levels") or [""])[0])
    geography = str((filters.get("geography") or [""])[0])
    role_family = infer_role_family(role_title)
    expanded: list[CollectionRequest] = []
    for request in official:
        for company in companies:
            source = {
                **request.source,
                "source_id": f"{request.source_id}-{slugify(str(company))}",
                "target_company": str(company),
                "target": {
                    "company": str(company),
                    "role_family": role_family,
                    "role_title": role_title,
                    "level": level,
                    "geography": geography,
                },
            }
            expanded.append(
                CollectionRequest(
                    source=source,
                    topic=request.topic,
                    run_date=request.run_date,
                    depth=request.depth,
                    max_results=request.max_results,
                )
            )
    return [*non_official, *expanded]


def infer_role_family(role_title: str) -> str:
    normalized = role_title.lower()
    if any(value in normalized for value in ("ai", "machine learning", "ml", "research")):
        return "machine_learning"
    if "data" in normalized:
        return "data_engineering"
    return "software_engineering"


def build_job_market_snapshot_from_run(
    rows: list[dict[str, Any]],
    *,
    scope: dict[str, Any],
    execution_report: dict[str, Any],
    unsupported_sources: list[str] | None = None,
) -> dict[str, Any]:
    requested = [str(value) for value in (scope.get("filters") or {}).get("companies") or []]
    outcomes: dict[str, list[str]] = {}
    for record in execution_report.get("requests") or []:
        company = str(record.get("target_company") or "")
        if not company:
            continue
        outcomes.setdefault(company, []).append(str(record.get("status") or ""))
    successful = {"ok", "warning", "cache_hit"}
    checked = [
        company
        for company, statuses in outcomes.items()
        if any(status in successful for status in statuses)
    ]
    failed = [
        company
        for company, statuses in outcomes.items()
        if not any(status in successful for status in statuses)
    ]
    return build_job_market_snapshot(
        rows,
        scope=scope,
        requested_sources=requested,
        checked_sources=checked,
        failed_sources=failed,
        unsupported_sources=unsupported_sources or [],
    )


def build_repair_failures(
    *,
    query_plan: dict[str, Any],
    rows: list[dict[str, Any]],
    execution_report: dict[str, Any],
    quality_report: dict[str, Any],
) -> list[dict[str, Any]]:
    records_by_query: dict[str, list[dict[str, Any]]] = {}
    for record in execution_report.get("requests") or []:
        query_id = str(record.get("query_id") or "")
        if query_id and str(record.get("pass_id") or "pass-1") == "pass-1":
            records_by_query.setdefault(query_id, []).append(record)
    coverage_by_facet = {
        str(facet.get("facet_id") or ""): facet
        for facet in (quality_report.get("facet_coverage") or {}).get("facets") or []
    }
    failures: list[dict[str, Any]] = []
    for query in query_plan.get("queries") or []:
        if not query.get("required"):
            continue
        query_id = str(query.get("query_id") or "")
        facet_id = str(query.get("facet_id") or "")
        records = records_by_query.get(query_id, [])
        failed_statuses = {
            "failed",
            "rate_limit",
            "retry_exhausted",
            "robots_denied",
            "timeout",
        }
        if not records or all(
            str(record.get("status") or "") in failed_statuses for record in records
        ):
            failures.append({"facet_id": facet_id, "reason": "no_executable_sources"})
            continue
        facet_rows = [row for row in rows if str(row.get("facet_id") or "") == facet_id]
        if canonical_failure := build_canonical_refetch_failure(
            facet_rows,
            facet_id=facet_id,
        ):
            failures.append(canonical_failure)
        canonical_rows = [
            row for row in facet_rows if row.get("source_class") != "discovery_only"
        ]
        if query.get("freshness_window_days") is not None and canonical_rows and all(
            str(row.get("freshness_status") or "") != "fresh"
            for row in canonical_rows
        ):
            failures.append({"facet_id": facet_id, "reason": "freshness_failure"})
        coverage = coverage_by_facet.get(facet_id)
        if coverage is not None and not coverage.get("evidence_ids"):
            failures.append({"facet_id": facet_id, "reason": "no_relevant_evidence"})
            continue
        relevant = [
            row
            for row in facet_rows
            if row.get("claim_eligible") is not False
            and float(row.get("relevance_score") or 0.0) >= 0.15
        ]
        if (
            query_plan.get("profile") != "job_market"
            and len(relevant) >= 2
            and len({build_independence_key(row) for row in relevant}) == 1
        ):
            failures.append({"facet_id": facet_id, "reason": "source_concentration"})
    return failures


def build_canonical_refetch_failure(
    facet_rows: list[dict[str, Any]],
    *,
    facet_id: str,
) -> dict[str, Any] | None:
    """Describe failed attempted canonical lineages and unused next candidates."""

    discovery_rows = [
        row
        for row in facet_rows
        if row.get("source_class") == "discovery_only"
        and row.get("connector") == "web_search"
    ]
    attempted = {
        str(row.get("discovery_source_id")): row
        for row in discovery_rows
        if row.get("discovery_source_id")
    }
    if not attempted:
        return None
    successful = {
        str(row.get("discovery_source_id"))
        for row in facet_rows
        if row.get("connector") == "web_page"
        and row.get("source_class") != "discovery_only"
        and row.get("discovery_source_id")
        and row.get("content_valid") is not False
        and row.get("content_invalid") is not True
        and bool(str(row.get("text") or "").strip())
    }
    failed_ids = [lineage_id for lineage_id in attempted if lineage_id not in successful]
    if not failed_ids:
        return None
    attempted_urls = {
        canonicalize_url(str(row.get("url") or "")) for row in attempted.values()
    }
    next_by_canonical: dict[str, str] = {}
    for row in discovery_rows:
        url = str(row.get("url") or "")
        parsed = urlsplit(url)
        canonical = canonicalize_url(url)
        if (
            not row.get("discovery_source_id")
            and parsed.scheme in {"http", "https"}
            and parsed.netloc
            and canonical not in attempted_urls
        ):
            next_by_canonical.setdefault(canonical, url)
    next_urls = list(next_by_canonical.values())
    return {
        "facet_id": facet_id,
        "reason": "canonical_refetch_failure",
        "failed_discovery_source_ids": failed_ids,
        "next_candidate_urls": next_urls,
    }


def reconcile_query_plan(
    query_plan: dict[str, Any], execution_report: dict[str, Any]
) -> None:
    """Record an explicit terminal state for every planned query."""

    records_by_query: dict[str, list[dict[str, Any]]] = {}
    for record in execution_report.get("requests") or []:
        query_id = str(record.get("query_id") or "")
        if query_id and str(record.get("pass_id") or "pass-1") == "pass-1":
            records_by_query.setdefault(query_id, []).append(record)

    counts = {"planned": 0, "executed": 0, "failed": 0, "skipped": 0}
    provider_disabled = str(query_plan.get("search_provider") or "none") in {"", "none"}
    for query in query_plan.get("queries") or []:
        counts["planned"] += 1
        records = records_by_query.get(str(query.get("query_id") or ""), [])
        statuses = {str(record.get("status") or "unknown") for record in records}
        if records:
            query["execution_statuses"] = sorted(statuses)
            failed_statuses = {"failed", "retry_exhausted", "timeout"}
            if statuses and statuses.issubset(failed_statuses):
                query["status"] = "failed"
                counts["failed"] += 1
            else:
                query["status"] = "executed"
                counts["executed"] += 1
            continue
        only_web_search = set(query.get("source_types") or ["web_search"]) == {"web_search"}
        query["status"] = "skipped"
        query["skip_reason"] = (
            "search_provider_disabled"
            if provider_disabled and only_web_search
            else "not_executed"
        )
        counts["skipped"] += 1
    query_plan["query_reconciliation"] = counts


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
            source_evidence_id = str(normalized.get("evidence_id") or "")
            if source_evidence_id and not normalized.get("source_evidence_id"):
                normalized["source_evidence_id"] = source_evidence_id
            normalized["evidence_id"] = f"ev-{len(rows) + 1:04d}"
            rows.append(normalized)
    return rows


def enrich_rows_with_freshness(
    rows: list[dict[str, Any]],
    *,
    query_plan: dict[str, Any],
    as_of: str,
) -> list[dict[str, Any]]:
    windows: dict[str, int | None] = {}
    for query in query_plan.get("queries") or []:
        facet_id = str(query.get("facet_id") or "")
        window = query.get("freshness_window_days")
        windows[facet_id] = int(window) if window is not None else None
    enriched: list[dict[str, Any]] = []
    for row in rows:
        facet_id = str(row.get("facet_id") or "")
        window = windows.get(facet_id)
        fresh = enrich_row_freshness(row, as_of=as_of, window_days=window)
        fresh["freshness_window_days"] = window
        enriched.append(fresh)
    return enriched


def build_evidence_chunks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for row in rows:
        blocks = row.get("content_blocks")
        if not isinstance(blocks, list) or not blocks:
            continue
        parent_evidence_id = str(row.get("evidence_id") or "")
        inherited = {
            key: value
            for key, value in row.items()
            if key
            not in {
                "content_blocks",
                "evidence_id",
                "structured_data",
                "tables",
                "text",
                "text_excerpt",
            }
        }
        for chunk in build_chunks(
            blocks,
            parent_evidence_id=parent_evidence_id,
        ):
            chunk_id = str(chunk["chunk_id"])
            heading = str(chunk.get("heading") or "")
            chunks.append(
                {
                    **inherited,
                    **chunk,
                    "evidence_id": chunk_id,
                    "source_evidence_id": parent_evidence_id,
                    "parent_evidence_id": parent_evidence_id,
                    "is_chunk": True,
                    "record_kind": "evidence_chunk",
                    "title": " — ".join(
                        value
                        for value in (str(row.get("title") or ""), heading)
                        if value
                    ),
                }
            )
    return chunks


def build_analysis_rows(
    rows: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Use semantic chunks in place of truncated parents for analysis and citations."""

    chunked_parent_ids = {
        str(chunk.get("parent_evidence_id") or "") for chunk in chunks
    }
    unchunked = [
        row
        for row in rows
        if str(row.get("evidence_id") or "") not in chunked_parent_ids
    ]
    return [*unchunked, *chunks]


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
