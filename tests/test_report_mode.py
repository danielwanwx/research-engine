import json
import builtins
from pathlib import Path

import pytest

from research_engine.cli import main
from research_engine.optional_dependencies import MissingOptionalDependency
from research_engine.runner import ResearchEngine


def _evidence_file(tmp_path: Path, *, count: int = 1) -> Path:
    path = tmp_path / "evidence.jsonl"
    rows = [
        {
            "title": f"Evidence {index}",
            "url": f"https://source-{index}.example/evidence",
            "text": "Independent evidence supports the research question with enough detail.",
        }
        for index in range(count)
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return path


def test_default_python_run_writes_summary_without_documents(tmp_path):
    result = ResearchEngine(output_dir=tmp_path).run(
        "restaurant lease negotiation",
        run_date="2026-08-10",
        slug="default-summary",
        external_evidence_paths=[_evidence_file(tmp_path)],
        search_provider="none",
    )

    run_dir = Path(result.run_dir)
    assert result.report_mode == "summary"
    assert result.pdf_report_path == ""
    assert result.pdf_report_status == "not_requested"
    assert (run_dir / "research_summary.json").exists()
    assert not (run_dir / "research_report.md").exists()
    assert not (run_dir / "research_report.pdf").exists()
    assert not (run_dir / "pdf_report_status.json").exists()
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    assert manifest["report_mode"] == "summary"
    assert manifest["report"]["status"] == "not_requested"
    assert result.status == "complete"
    assert not any("PDF report" in warning for warning in result.warnings)


def test_summary_contains_conclusion_warnings_and_bounded_evidence(tmp_path):
    result = ResearchEngine(output_dir=tmp_path).run(
        "restaurant lease negotiation",
        run_date="2026-08-10",
        slug="summary-content",
        external_evidence_paths=[_evidence_file(tmp_path, count=25)],
        search_provider="none",
    )

    summary = json.loads((Path(result.run_dir) / "research_summary.json").read_text())
    assert summary["schema_version"] == "research_summary.v1"
    assert summary["run_id"] == result.run_id
    assert summary["headline"]
    assert summary["confidence"]
    assert isinstance(summary["rationale"], list)
    assert isinstance(summary["quality_warnings"], list)
    assert isinstance(summary["scope_warnings"], list)
    assert len(summary["key_evidence"]) <= 10
    assert all(
        set(reference) == {"evidence_id", "title", "url", "quality_tier"}
        for reference in summary["key_evidence"]
    )
    assert summary["loop_status"] == json.loads(
        (Path(result.run_dir) / "loop_record.json").read_text()
    )["loop_status"]


def test_full_report_mode_preserves_documents_and_pdf(tmp_path):
    result = ResearchEngine(output_dir=tmp_path).run(
        "restaurant lease negotiation",
        report_mode="full",
        run_date="2026-08-10",
        slug="full-report",
        external_evidence_paths=[_evidence_file(tmp_path)],
        search_provider="none",
    )

    run_dir = Path(result.run_dir)
    assert result.report_mode == "full"
    assert result.pdf_report_status == "generated"
    assert result.pdf_report_path.endswith("research_report.pdf")
    assert (run_dir / "research_summary.json").exists()
    assert (run_dir / "research_report.md").exists()
    assert (run_dir / "research_report.pdf").exists()
    assert json.loads((run_dir / "pdf_report_status.json").read_text())["status"] == "generated"
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    assert manifest["report_mode"] == "full"
    assert manifest["report"]["markdown"]["status"] == "generated"
    assert manifest["report"]["pdf"]["status"] == "generated"


def test_invalid_report_mode_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="report_mode"):
        ResearchEngine(output_dir=tmp_path).run(
            "invalid mode",
            report_mode="invalid",
        )


def test_cli_report_mode_defaults_to_summary_and_accepts_full(tmp_path, capsys):
    exit_code = main(
        [
            "run",
            "restaurant lease negotiation",
            "--pack",
            "auto",
            "--dry-run",
            "--output",
            str(tmp_path),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["report_mode"] == "summary"

    full_dir = tmp_path / "full"
    exit_code = main(
        [
            "run",
            "restaurant lease negotiation",
            "--pack",
            "auto",
            "--dry-run",
            "--report-mode",
            "full",
            "--output",
            str(full_dir),
        ]
    )
    full_payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert full_payload["report_mode"] == "full"
    assert (full_dir / full_payload["run_id"] / "research_report.md").exists()


def test_summary_mode_does_not_import_reportlab(tmp_path, monkeypatch):
    real_import = builtins.__import__

    def reject_reportlab(name, *args, **kwargs):
        if name == "reportlab" or name.startswith("reportlab."):
            raise ModuleNotFoundError("reportlab is not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_reportlab)
    result = ResearchEngine(output_dir=tmp_path).run(
        "summary without report renderer",
        dry_run=True,
        run_date="2026-08-10",
        slug="core-only",
    )

    assert result.report_mode == "summary"
    assert (Path(result.run_dir) / "research_summary.json").exists()


def test_full_mode_missing_report_extra_has_actionable_error(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "research_engine.optional_dependencies.importlib.util.find_spec",
        lambda name: None if name == "reportlab" else None,
    )

    with pytest.raises(MissingOptionalDependency, match=r"pip install research-engine\[report\]"):
        ResearchEngine(output_dir=tmp_path).run(
            "full report without optional dependency",
            report_mode="full",
            dry_run=True,
        )
    assert not list(tmp_path.iterdir())


def test_cli_full_mode_missing_report_extra_is_concise(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        "research_engine.optional_dependencies.importlib.util.find_spec",
        lambda name: None if name == "reportlab" else None,
    )

    exit_code = main(
        [
            "run",
            "full report without optional dependency",
            "--report-mode",
            "full",
            "--dry-run",
            "--output",
            str(tmp_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "pip install research-engine[report]" in captured.err
    assert captured.out == ""


def test_research_engine_skill_reads_summary_and_requires_explicit_full_report():
    skill = Path(__file__).parents[1] / "skills" / "research-engine" / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    assert "--report-mode summary" in text
    assert "research_summary.json" in text
    assert "`--report-mode full` only when" in text
