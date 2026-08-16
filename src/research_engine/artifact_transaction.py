"""Persistence boundaries for run directories and optional reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from research_engine.artifacts import render_report, write_json, write_jsonl
from research_engine.models import utc_now
from research_engine.security import redact_text


def not_requested_pdf_status() -> dict[str, Any]:
    """Return the compatibility status used when document output was not requested."""

    return {
        "schema_version": "pdf_report_status.v1",
        "status": "not_requested",
        "path": "",
        "generated_at": utc_now(),
        "page_count": 0,
        "byte_count": 0,
        "font_mode": "",
        "error_type": "",
        "error_message": "",
    }


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


def write_core_artifacts(
    run_dir: Path,
    *,
    manifest: dict[str, Any],
    query_plan: dict[str, Any],
    execution_report: dict[str, Any],
    cost_record: dict[str, Any],
    repair_record: dict[str, Any],
    auth_challenges: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    quality_report: dict[str, Any],
    claim_review: dict[str, Any],
    job_market_snapshot: dict[str, Any] | None,
    matrix: dict[str, Any],
    decision_brief: dict[str, Any],
    loop_contract: dict[str, Any],
    loop_record: dict[str, Any],
) -> None:
    """Persist the deterministic run artifacts before optional report output."""

    write_json(run_dir / "run_manifest.json", manifest)
    write_json(run_dir / "query_plan.json", query_plan)
    write_json(run_dir / "collection_execution.json", execution_report)
    write_json(run_dir / "cost_record.json", cost_record)
    write_json(run_dir / "repair_record.json", repair_record)
    write_jsonl(run_dir / "auth_challenges.jsonl", auth_challenges)
    write_jsonl(run_dir / "evidence.jsonl", rows)
    write_jsonl(run_dir / "chunks.jsonl", chunks)
    write_json(run_dir / "evidence_quality.json", quality_report)
    write_json(run_dir / "facet_coverage.json", dict(quality_report.get("facet_coverage") or {}))
    write_json(run_dir / "claim_review.json", claim_review)
    if job_market_snapshot is not None:
        write_json(run_dir / "job_market_snapshot.json", job_market_snapshot)
    write_json(run_dir / "supply_demand_matrix.json", matrix)
    write_json(run_dir / "decision_brief.json", decision_brief)
    write_json(run_dir / "loop_contract.json", loop_contract)
    write_json(run_dir / "loop_record.json", loop_record)


def write_summary_and_report(
    run_dir: Path,
    *,
    summary: dict[str, Any],
    report_mode: str,
    topic: str,
    pack_id: str,
    raw_rows: list[dict[str, Any]],
    claim_review: dict[str, Any],
    decision_brief: dict[str, Any],
    quality_report: dict[str, Any],
    loop_record: dict[str, Any],
    status: str,
    profile: str,
    as_of: str,
    facet_coverage: dict[str, Any],
    job_market_snapshot: dict[str, Any] | None,
    pdf_renderer: Callable[[Path], dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Write the bounded summary and, only when requested, human reports."""

    write_json(run_dir / "research_summary.json", summary)
    if report_mode == "summary":
        pdf_status = not_requested_pdf_status()
        report_status = {
            "status": "not_requested",
            "markdown": {"status": "not_requested", "path": ""},
            "pdf": pdf_status,
        }
        return pdf_status, report_status

    (run_dir / "research_report.md").write_text(
        render_report(
            topic=topic,
            pack_id=pack_id,
            raw_rows=raw_rows,
            claim_review=claim_review,
            decision_brief=decision_brief,
            quality_report=quality_report,
            loop_record=loop_record,
            status=status,
            profile=profile,
            as_of=as_of,
            facet_coverage=facet_coverage,
            job_market_snapshot=job_market_snapshot,
        ),
        encoding="utf-8",
    )
    pdf_status = pdf_renderer(run_dir)
    pdf_status["error_message"] = redact_text(pdf_status.get("error_message") or "")
    report_status = {
        "status": "generated" if pdf_status.get("status") == "generated" else "failed",
        "markdown": {"status": "generated", "path": "research_report.md"},
        "pdf": pdf_status,
    }
    write_json(run_dir / "pdf_report_status.json", pdf_status)
    return pdf_status, report_status
