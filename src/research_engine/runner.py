"""Research Engine runner."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Callable

from research_engine.artifacts import render_report, slugify, write_json, write_jsonl
from research_engine.connectors import FinanceQuoteConnector, ManualConnector, WebPageConnector
from research_engine.models import CollectionRequest, CollectionResult, ResearchRunResult, utc_now
from research_engine.packs import build_pack_queries, pack_summary, select_research_pack
from research_engine.quality import enrich_rows_with_quality
from research_engine.synthesis import (
    build_claim_review,
    build_decision_brief,
    build_supply_demand_matrix,
)


ConnectorProvider = Any | Callable[[], Any]

DEFAULT_CONNECTORS: dict[str, ConnectorProvider] = {
    FinanceQuoteConnector.connector_id: FinanceQuoteConnector,
    ManualConnector.connector_id: ManualConnector,
    WebPageConnector.connector_id: WebPageConnector,
}

DEPTH_MAX_RESULTS = {"quick": 3, "deep": 8, "audit": 12}


class ResearchEngine:
    def __init__(
        self,
        *,
        pack_dir: Path | None = None,
        output_dir: Path | None = None,
        connectors: dict[str, ConnectorProvider] | None = None,
    ) -> None:
        self.pack_dir = pack_dir
        self.output_dir = output_dir or Path("runs")
        self.connector_factories = {**DEFAULT_CONNECTORS, **(connectors or {})}

    def run(
        self,
        topic: str,
        *,
        depth: str = "quick",
        dry_run: bool = False,
        pack_id: str | None = None,
        run_date: str | None = None,
        slug: str | None = None,
    ) -> ResearchRunResult:
        if depth not in DEPTH_MAX_RESULTS:
            supported = ", ".join(sorted(DEPTH_MAX_RESULTS))
            raise ValueError(f"unsupported depth: {depth}; supported: {supported}")
        selected_pack = select_research_pack(topic, pack_dir=self.pack_dir, pack_id=pack_id)
        resolved_date = run_date or date.today().isoformat()
        run_id = f"{resolved_date}-{slug or slugify(topic)}"
        run_dir = self.output_dir / run_id
        max_results = DEPTH_MAX_RESULTS[depth]
        source_requests = build_source_requests(selected_pack, topic=topic)
        query_plan = {
            "topic": topic,
            "pack": pack_summary(selected_pack),
            "depth": depth,
            "max_results_per_source": max_results,
            "queries": build_pack_queries(topic, selected_pack),
            "sources": [
                {
                    "source_id": request.source_id,
                    "connector": request.source.get("connector"),
                }
                for request in source_requests
            ],
        }
        collection_results: list[CollectionResult] = []
        warnings: list[str] = []
        if not dry_run and not source_requests:
            warnings.append(f"research pack {selected_pack.get('id')} has no executable sources")
        if not dry_run:
            for source in source_requests:
                connector_id = str(source.source.get("connector") or "")
                provider = self.connector_factories.get(connector_id)
                if not provider:
                    warnings.append(f"no connector registered for {connector_id}")
                    continue
                connector = provider() if callable(provider) else provider
                try:
                    result = connector.collect(
                        CollectionRequest(
                            source=source.source,
                            topic=topic,
                            run_date=resolved_date,
                            depth=depth,
                            max_results=max_results,
                        )
                    )
                except Exception as exc:
                    warnings.append(f"{connector_id} connector crashed for {source.source_id}: {exc}")
                    continue
                collection_results.append(result)
                warnings.extend(result.warnings)
        rows = normalize_rows(collection_results)
        rows, quality_report = enrich_rows_with_quality(rows, topic=topic, pack=selected_pack)
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
        status = run_status(dry_run=dry_run, rows=rows, warnings=warnings, source_requests=source_requests)
        manifest = {
            "run_id": run_id,
            "topic": topic,
            "created_at": utc_now(),
            "status": status,
            "pack": pack_summary(selected_pack),
            "warnings": warnings,
            "quality_summary": {
                "average_quality_score": quality_report.get("average_quality_score"),
                "duplicate_cluster_count": quality_report.get("duplicate_cluster_count"),
                "conflict_flag_count": len(quality_report.get("conflict_flags") or []),
            },
        }
        write_json(run_dir / "run_manifest.json", manifest)
        write_json(run_dir / "query_plan.json", query_plan)
        write_jsonl(run_dir / "evidence.jsonl", rows)
        write_json(run_dir / "evidence_quality.json", quality_report)
        write_json(run_dir / "claim_review.json", claim_review)
        write_json(run_dir / "supply_demand_matrix.json", matrix)
        write_json(run_dir / "decision_brief.json", decision_brief)
        (run_dir / "research_report.md").write_text(
            render_report(
                topic=topic,
                pack_id=str(selected_pack.get("id")),
                raw_rows=rows,
                claim_review=claim_review,
                decision_brief=decision_brief,
                quality_report=quality_report,
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
            warnings=warnings,
        )


def run_research(topic: str, **kwargs: Any) -> ResearchRunResult:
    return ResearchEngine(**kwargs.pop("engine_kwargs", {})).run(topic, **kwargs)


def build_source_requests(pack: dict[str, Any], *, topic: str) -> list[CollectionRequest]:
    sources: list[dict[str, Any]] = []
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
    return "failed_no_rows" if warnings else "complete_empty"
