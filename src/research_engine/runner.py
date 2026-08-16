"""Research Engine runner."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import re
from typing import Any, Callable
from urllib.parse import urlsplit

from research_engine.artifacts import build_research_summary, slugify, write_json
from research_engine.artifact_transaction import (
    not_requested_pdf_status as _not_requested_pdf_status,
    reserve_run_dir,
    write_core_artifacts,
    write_summary_and_report,
)
from research_engine.collection_pipeline import CollectionPipeline
from research_engine.conflicts import build_independence_key
from research_engine.connectors import (
    AgentReachBridgeConnector,
    AnySearchConnector,
    AuthenticatedBrowserConnector,
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
from research_engine.browser_recipes import recipe_for_platform, recipe_for_url
from research_engine.execution import ConnectorExecutionOptions
from research_engine.job_market import build_job_market_snapshot
from research_engine.loop import build_loop_contract, build_loop_record
from research_engine.models import CollectionRequest, CollectionResult, ResearchRunResult, utc_now
from research_engine.optional_dependencies import require_report_dependency
from research_engine.packs import pack_summary, select_research_pack
from research_engine.pdf_report import render_pdf_report
from research_engine.planning import build_query_plan, collection_requests_from_plan
from research_engine.platforms import build_platform_research_plan, pack_platforms_for_depth
from research_engine.quality import canonicalize_url, enrich_rows_with_quality
from research_engine.repair import build_repair_plan, progress_fingerprint
from research_engine.security import (
    artifact_path_ref,
    redact_text,
    sanitize_for_artifact,
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

from research_engine.evaluation_pipeline import (
    build_analysis_rows,
    build_evidence_chunks,
    enrich_rows_with_freshness,
    normalize_rows,
    run_status,
    sanitize_rows_for_artifacts,
)

not_requested_pdf_status = _not_requested_pdf_status
ConnectorProvider = Any | Callable[[], Any]

DEFAULT_CONNECTORS: dict[str, ConnectorProvider] = {
    AgentReachBridgeConnector.connector_id: AgentReachBridgeConnector,
    AnySearchConnector.connector_id: AnySearchConnector,
    AuthenticatedBrowserConnector.connector_id: AuthenticatedBrowserConnector,
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
REPORT_MODES = frozenset({"summary", "full"})


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
        self.collection_pipeline = CollectionPipeline(
            connector_providers=self.connector_factories,
            options=self.execution_options,
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
        anysearch_discovery: bool = False,
        paid_discovery: bool = False,
        paid_call_budget: int = 0,
        agent_reach: bool = False,
        agent_reach_command_templates: list[str] | None = None,
        research_scope: dict[str, Any] | None = None,
        search_provider: str = "none",
        search_endpoint: str = "",
        as_of: str | None = None,
        browser_auth: str = "auto",
        report_mode: str = "summary",
    ) -> ResearchRunResult:
        if depth not in DEPTH_MAX_RESULTS:
            supported = ", ".join(sorted(DEPTH_MAX_RESULTS))
            raise ValueError(f"unsupported depth: {depth}; supported: {supported}")
        if browser_auth not in {"auto", "never"}:
            raise ValueError("browser_auth must be 'auto' or 'never'")
        if report_mode not in REPORT_MODES:
            supported = ", ".join(sorted(REPORT_MODES))
            raise ValueError(f"unsupported report_mode: {report_mode}; supported: {supported}")
        if report_mode == "full":
            require_report_dependency()
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
        effective_pack_platforms = pack_platforms_for_depth(selected_pack, depth)
        platform_plan = build_platform_research_plan(
            topic,
            scope=platform_scope,
            pack=selected_pack,
            depth=depth,
        )
        source_requests = build_source_requests(
            selected_pack,
            topic=topic,
            external_evidence_paths=external_evidence_paths,
            platform_plan=platform_plan,
            github_public=platform_scope == "all",
            web_search_pages=web_search_pages,
            target=resolved_target,
            paid_discovery=False,
            paid_call_budget=0,
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
                "anysearch_discovery": bool(resolved_target and anysearch_discovery),
                "xai_discovery": bool(
                    resolved_target and paid_discovery and paid_call_budget > 0
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
                "authenticated_browser": browser_auth == "auto",
            },
            "browser_auth": browser_auth,
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
                        "source_id": "anysearch_target_discovery",
                        "connector": "anysearch_discovery",
                        "conditional": True,
                    }
                ]
                if resolved_target and anysearch_discovery
                else []
            )
            + (
                [
                    {
                        "source_id": "xai_target_discovery",
                        "connector": "xai_discovery",
                        "conditional": True,
                        "paid": True,
                    }
                ]
                if resolved_target and paid_discovery and paid_call_budget > 0
                else []
            )
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
            )
            + (
                [
                    {
                        "source_id": "browser_authenticated_recovery",
                        "connector": "authenticated_browser",
                        "conditional": True,
                    }
                ]
                if browser_auth == "auto"
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
        auth_challenges: list[dict[str, Any]] = []
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
            collection_results, execution_warnings, execution_report = (
                self.collection_pipeline.execute(executable_requests)
            )
            warnings.extend(execution_warnings)
            if resolved_target:
                if target_needs_supplemental_discovery(
                    collection_results,
                    target=resolved_target,
                    run_date=resolved_date,
                ):
                    supplemental_requests = build_target_supplemental_requests(
                        target=resolved_target,
                        topic=topic,
                        run_date=resolved_date,
                        depth=depth,
                        max_results=max_results,
                        anysearch_discovery=anysearch_discovery,
                        paid_discovery=paid_discovery,
                        paid_call_budget=paid_call_budget,
                    )
                    if supplemental_requests:
                        supplemental_results, supplemental_warnings, supplemental_report = (
                            self.collection_pipeline.execute(supplemental_requests)
                        )
                        collection_results.extend(supplemental_results)
                        warnings.extend(supplemental_warnings)
                        execution_report = self.collection_pipeline.merge_reports(
                            execution_report,
                            supplemental_report,
                        )
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
                    refetch_results, refetch_warnings, refetch_report = (
                        self.collection_pipeline.execute([refetch_request])
                    )
                    collection_results.extend(refetch_results)
                    warnings.extend(refetch_warnings)
                    execution_report = self.collection_pipeline.merge_reports(
                        execution_report, refetch_report
                    )
            elif not resolved_target:
                canonical_request = build_canonical_refetch_request(
                    collection_results,
                    topic=topic,
                    run_date=resolved_date,
                    depth=depth,
                    max_results=int((m2_plan.get("budget") or {}).get("max_canonical_refetches") or 0),
                )
                if canonical_request:
                    refetch_results, refetch_warnings, refetch_report = (
                        self.collection_pipeline.execute([canonical_request])
                    )
                    collection_results.extend(refetch_results)
                    warnings.extend(refetch_warnings)
                    execution_report = self.collection_pipeline.merge_reports(
                        execution_report, refetch_report
                    )
            browser_requests = build_authenticated_browser_requests(
                collection_results,
                platform_plan=platform_plan,
                topic=topic,
                run_date=resolved_date,
                depth=depth,
                max_results=max_results,
                browser_auth=browser_auth,
                pack_platforms=effective_pack_platforms,
            )
            if browser_requests:
                source_requests.extend(browser_requests)
                browser_pipeline = CollectionPipeline(
                    connector_providers=self.connector_factories,
                    options=browser_execution_options(),
                )
                browser_results, browser_warnings, browser_report = browser_pipeline.execute(
                    browser_requests
                )
                collection_results.extend(browser_results)
                warnings.extend(browser_warnings)
                execution_report = self.collection_pipeline.merge_reports(
                    execution_report, browser_report
                )
                auth_challenges = auth_challenges_from_results(browser_results)
            if not source_requests:
                warnings.append(
                    f"research pack {selected_pack.get('id')} has no executable sources"
                )
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
                        self.collection_pipeline.execute(repair_requests)
                    )
                    collection_results.extend(repair_results)
                    warnings.extend(repair_warnings)
                    execution_report = self.collection_pipeline.merge_reports(
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
                            self.collection_pipeline.execute([repair_refetch])
                        )
                        collection_results.extend(repaired_pages)
                        warnings.extend(refetch_warnings)
                        execution_report = self.collection_pipeline.merge_reports(
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
        query_plan["auth_challenge_summary"] = summarize_auth_challenges(auth_challenges)
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
        apply_auth_coverage_confidence_ceiling(claim_review, auth_challenges)
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
            "report_mode": report_mode,
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
                "auth_challenges": len(auth_challenges),
                "pending_human_actions": query_plan["auth_challenge_summary"][
                    "pending_human_actions"
                ],
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
        write_core_artifacts(
            run_dir,
            manifest=manifest,
            query_plan=query_plan,
            execution_report=execution_report,
            cost_record=cost_record,
            repair_record=repair_record,
            auth_challenges=auth_challenges,
            rows=rows,
            chunks=chunks,
            quality_report=quality_report,
            claim_review=claim_review,
            job_market_snapshot=job_market_snapshot,
            matrix=matrix,
            decision_brief=decision_brief,
            loop_contract=loop_contract,
            loop_record=loop_record,
        )
        summary = build_research_summary(
            run_id=run_id,
            topic=topic,
            pack=pack_summary(selected_pack),
            profile=str(query_plan.get("profile") or "generic"),
            status=status,
            as_of=resolved_as_of,
            decision_brief=decision_brief,
            claim_review=claim_review,
            quality_report=quality_report,
            loop_record=loop_record,
            rows=rows,
            facet_coverage=dict(quality_report.get("facet_coverage") or {}),
        )
        pdf_status, report_status = write_summary_and_report(
            run_dir,
            summary=summary,
            report_mode=report_mode,
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
            pdf_renderer=render_pdf_report,
        )
        if pdf_status.get("status") != "generated" and report_mode == "full":
            warnings.append(
                "PDF report generation failed: "
                f"{pdf_status.get('error_type') or 'unknown_error'}"
            )
        manifest["warnings"] = warnings
        manifest["report_mode"] = report_mode
        manifest["report"] = report_status
        # Keep the legacy top-level PDF field for consumers of the pre-summary contract.
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
            pdf_report_status=str(pdf_status.get("status") or "not_requested"),
            report_mode=report_mode,
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
    paid_discovery: bool = False,
    paid_call_budget: int = 0,
    agent_reach: bool = False,
    agent_reach_command_templates: list[str] | None = None,
) -> list[CollectionRequest]:
    sources: list[dict[str, Any]] = []
    if target:
        sources.append(
            {
                "source_id": "official_job_discovery",
                "connector": "official_job_discovery",
                "target": target.as_dict(),
                "source_kind": "official_target_discovery",
                "access_mode": "public_official_endpoints",
                "cache_ttl_seconds": TARGET_DISCOVERY_CACHE_TTL_SECONDS,
            }
        )
        if paid_discovery and paid_call_budget > 0:
            sources.append(
                {
                    "source_id": "xai_target_discovery",
                    "connector": "xai_discovery",
                    "target": target.as_dict(),
                    "timeout_seconds": 75.0,
                    "source_kind": "dynamic_public_discovery",
                    "access_mode": "xai_web_search",
                    "paid_call": True,
                    "paid_call_approved": True,
                    "paid_call_budget": int(paid_call_budget),
                    "cache_ttl_seconds": TARGET_DISCOVERY_CACHE_TTL_SECONDS,
                }
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


def build_target_supplemental_requests(
    *,
    target: ResearchTarget,
    topic: str,
    run_date: str,
    depth: str,
    max_results: int,
    anysearch_discovery: bool,
    paid_discovery: bool,
    paid_call_budget: int,
) -> list[CollectionRequest]:
    sources: list[dict[str, Any]] = []
    if anysearch_discovery:
        sources.append(
            {
                "source_id": "anysearch_target_discovery",
                "connector": "anysearch_discovery",
                "target": target.as_dict(),
                "query_intent": "official_role",
                "timeout_seconds": 20.0,
                "source_kind": "dynamic_public_discovery",
                "access_mode": "anysearch_public_search",
                "external_discovery_approved": True,
                "cache_ttl_seconds": TARGET_DISCOVERY_CACHE_TTL_SECONDS,
            }
        )
    if paid_discovery and paid_call_budget > 0:
        sources.append(
            {
                "source_id": "xai_target_discovery",
                "connector": "xai_discovery",
                "target": target.as_dict(),
                "timeout_seconds": 45.0,
                "source_kind": "dynamic_public_discovery",
                "access_mode": "xai_web_search",
                "paid_call": True,
                "paid_call_approved": True,
                "paid_call_budget": int(paid_call_budget),
                "cache_ttl_seconds": TARGET_DISCOVERY_CACHE_TTL_SECONDS,
            }
        )
    return [
        CollectionRequest(
            source=source,
            topic=topic,
            run_date=run_date,
            depth=depth,
            max_results=max_results,
        )
        for source in sources
    ]


def target_needs_supplemental_discovery(
    results: list[CollectionResult],
    *,
    target: ResearchTarget,
    run_date: str,
) -> bool:
    rows = classify_target_evidence(
        normalize_rows(results),
        target=target,
        run_date=run_date,
    )
    return not any(
        "current_official_role" in (row.get("claim_fitness") or {}).get("eligible_claims", [])
        for row in rows
    )


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
        if row.get("connector") not in {"anysearch_discovery", "xai_discovery"}:
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
            "cache_ttl_seconds": TARGET_DISCOVERY_CACHE_TTL_SECONDS,
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
            infrastructure_reasons = sorted(
                {
                    str(record.get("failure_reason") or "")
                    for record in records
                    if str(record.get("failure_reason") or "")
                    in {
                        "dns_resolution_failed",
                        "network_timeout",
                        "network_unavailable",
                        "tls_failure",
                    }
                }
            )
            if infrastructure_reasons:
                failures.append(
                    {
                        "facet_id": facet_id,
                        "reason": "infrastructure_unavailable",
                        "failure_reasons": infrastructure_reasons,
                    }
                )
                continue
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


RECOVERABLE_BROWSER_REASONS = {
    "access_blocked",
    "browser_verification",
    "captcha",
    "enable_javascript",
    "human_verification",
    "javascript_shell",
    "login_wall",
    "security_check",
}
NON_RECOVERABLE_BROWSER_REASONS = {
    "access_denied",
    "paywall",
    "rate_limit",
    "robots_denied",
    "unusual_traffic",
}
RECIPE_TOPIC_ALIASES = {
    "linkedin": ("linkedin", "领英"),
    "x": ("twitter", "x.com"),
    "reddit": ("reddit",),
    "blind": ("teamblind", "blind forum"),
    "glassdoor": ("glassdoor",),
    "indeed": ("indeed",),
    "onepointthreeacres": ("1point3acres", "一亩三分地"),
    "hackernews": ("hacker news", "ycombinator news"),
    "github": ("github",),
    "stackoverflow": ("stack overflow", "stackoverflow"),
}


def browser_execution_options() -> ConnectorExecutionOptions:
    """Browser work is serialized and owns its bounded human-login timeout."""
    return ConnectorExecutionOptions(
        max_workers=1,
        retries=0,
        cache_dir=None,
        source_timeout_seconds=None,
        overall_deadline_seconds=None,
        host_max_concurrency=1,
        host_delay_seconds=0.0,
    )


def build_authenticated_browser_requests(
    results: list[CollectionResult],
    *,
    platform_plan: list[dict[str, Any]],
    topic: str,
    run_date: str,
    depth: str,
    max_results: int,
    browser_auth: str,
    pack_platforms: set[str],
) -> list[CollectionRequest]:
    if browser_auth != "auto":
        return []

    sources: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add_source(
        *,
        recipe_id: str,
        url: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        key = (recipe_id, canonicalize_url(url))
        if not url or key in seen:
            return
        seen.add(key)
        sources.append(
            {
                "source_id": f"browser_auth_{recipe_id}_{len(sources) + 1}",
                "connector": "authenticated_browser",
                "recipe_id": recipe_id,
                "target_url": url,
                "challenge_reason": reason,
                "source_kind": "authenticated_browser_recovery",
                "access_mode": "user_consented_browser",
                "pass_id": "browser-recovery",
                **dict(metadata or {}),
            }
        )

    for result in results:
        for row in result.rows:
            reasons = {
                str(reason) for reason in row.get("content_invalid_reasons") or [] if reason
            }
            if row.get("access_blocked") and not reasons:
                reasons.add("access_blocked")
            if reasons & NON_RECOVERABLE_BROWSER_REASONS:
                continue
            recoverable = sorted(reasons & RECOVERABLE_BROWSER_REASONS)
            if not recoverable:
                continue
            url = str(row.get("final_url") or row.get("url") or "")
            recipe = recipe_for_url(url)
            parsed = urlsplit(url)
            if not recipe and (parsed.scheme not in {"http", "https"} or not parsed.netloc):
                continue
            add_source(
                recipe_id=recipe.recipe_id if recipe else "generic",
                url=url,
                reason=recoverable[0],
                metadata={
                    key: row[key]
                    for key in ("query_id", "facet_id")
                    if row.get(key)
                },
            )

    for platform in platform_plan:
        platform_id = str(platform.get("platform") or "")
        recipe = recipe_for_platform(platform_id)
        if not recipe:
            continue
        explicitly_requested = topic_mentions_recipe(topic, recipe.recipe_id)
        pack_requested = platform_id in pack_platforms
        if not explicitly_requested and not pack_requested:
            continue
        url = str(platform.get("search_url") or recipe.search_url(topic))
        add_source(
            recipe_id=recipe.recipe_id,
            url=url,
            reason=(
                "explicit_platform_request"
                if explicitly_requested
                else "pack_platform_priority"
            ),
            metadata={
                "query": str(platform.get("query") or topic),
                "platform": platform_id,
                "auth_gate_policy": (
                    "blocking" if explicitly_requested else "advisory"
                ),
            },
        )

    for recipe_id in RECIPE_TOPIC_ALIASES:
        if not topic_mentions_recipe(topic, recipe_id):
            continue
        recipe = recipe_for_platform(recipe_id)
        if recipe:
            add_source(
                recipe_id=recipe.recipe_id,
                url=recipe.search_url(topic),
                reason="explicit_platform_request",
                metadata={"query": topic},
            )

    return [
        CollectionRequest(
            source=source,
            topic=topic,
            run_date=run_date,
            depth=depth,
            max_results=max_results,
        )
        for source in sources
    ]


def topic_mentions_recipe(topic: str, recipe_id: str) -> bool:
    normalized = str(topic).casefold()
    return any(alias.casefold() in normalized for alias in RECIPE_TOPIC_ALIASES.get(recipe_id, ()))


def auth_challenges_from_results(results: list[CollectionResult]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for result in results:
        for challenge in result.metadata.get("auth_challenges") or []:
            if not isinstance(challenge, dict):
                continue
            safe = sanitize_for_artifact(challenge)
            if not isinstance(safe, dict):
                continue
            challenge_id = str(safe.get("challenge_id") or "")
            if challenge_id:
                by_id[challenge_id] = safe
    return list(by_id.values())


def summarize_auth_challenges(challenges: list[dict[str, Any]]) -> dict[str, int]:
    statuses = [str(challenge.get("status") or "pending") for challenge in challenges]
    return {
        "total": len(challenges),
        "completed": statuses.count("completed"),
        "pending_human_actions": sum(
            bool(challenge.get("human_action_required"))
            and bool(challenge.get("blocking", True))
            and status != "completed"
            for challenge, status in zip(challenges, statuses)
        ),
        "advisory_coverage_gaps": sum(
            bool(challenge.get("coverage_missing"))
            and not bool(challenge.get("blocking", True))
            and status != "completed"
            for challenge, status in zip(challenges, statuses)
        ),
    }


def apply_auth_coverage_confidence_ceiling(
    claim_review: dict[str, Any],
    challenges: list[dict[str, Any]],
) -> None:
    """Bound confidence when a pack-scheduled authenticated source is missing."""
    missing_platforms = sorted(
        {
            str(challenge.get("recipe_id") or "authenticated_source")
            for challenge in challenges
            if challenge.get("coverage_missing") and not challenge.get("blocking", True)
        }
    )
    if not missing_platforms:
        return
    overall = claim_review.setdefault("overall", {})
    overall["confidence_ceiling"] = "medium"
    if overall.get("confidence") == "high":
        overall["confidence"] = "medium"
    risk_flags = overall.setdefault("risk_flags", [])
    for platform in missing_platforms:
        flag = f"{platform}_coverage_missing"
        if not any(str(value).startswith(flag) for value in risk_flags):
            risk_flags.append(flag)


def build_cost_record(
    execution_report: dict[str, Any],
    *,
    paid_discovery: bool,
    paid_call_budget: int,
) -> dict[str, Any]:
    attempts = 0
    completed = 0
    provider_usage: list[dict[str, Any]] = []
    stop_reasons: list[str] = []
    for record in execution_report.get("requests") or []:
        if str(record.get("connector") or "") != "xai_discovery":
            continue
        metadata = dict(record.get("provider_metadata") or {})
        if "paid_calls_attempted" in metadata:
            record_attempts = int(metadata.get("paid_calls_attempted") or 0)
            record_completed = int(metadata.get("paid_calls_completed") or 0)
        elif str(record.get("status") or "") in {"failed", "timeout"}:
            record_attempts = int(record.get("attempts") or 0)
            record_completed = 0
        else:
            record_attempts = 0
            record_completed = 0
        attempts += record_attempts
        completed += record_completed
        reason = str(metadata.get("stop_reason") or "")
        if reason:
            stop_reasons.append(reason)
        if record_attempts:
            provider_usage.append(
                {
                    "provider": "xai",
                    "model": str(metadata.get("model") or ""),
                    "usage": dict(metadata.get("usage") or {"status": "unknown"}),
                }
            )
    enabled = bool(paid_discovery and paid_call_budget > 0)
    if not enabled:
        stop_reason = "paid_discovery_disabled"
    elif attempts:
        stop_reason = "paid_call_completed" if completed else "paid_call_failed"
    elif stop_reasons:
        stop_reason = stop_reasons[0]
    else:
        stop_reason = "paid_discovery_not_needed"
    return {
        "paid_calls_allowed": max(0, int(paid_call_budget)) if enabled else 0,
        "paid_calls_attempted": attempts,
        "paid_calls_completed": completed,
        "provider_usage": provider_usage,
        "estimated_cost_usd": None,
        "budget_status": "within_budget" if enabled else "not_enabled",
        "stop_reason": stop_reason,
    }


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


def merge_execution_reports(*reports: dict[str, Any]) -> dict[str, Any]:
    """Compatibility wrapper for callers that used the former runner helper."""

    return CollectionPipeline.merge_reports(*reports)
