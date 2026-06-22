import json

from research_engine.cli import main
from research_engine.models import CollectionResult
from research_engine.runner import ResearchEngine


class FakeFinanceConnector:
    def collect(self, request):
        return CollectionResult(
            source_id=request.source_id,
            connector="finance_quote",
            rows=[
                {
                    "source_id": request.source_id,
                    "connector": "finance_quote",
                    "title": "MU quote",
                    "url": "https://finance.yahoo.com/quote/MU",
                    "text": "MU regular market price: 100 USD",
                    "metrics": {"symbol": "MU", "regular_market_price": 100},
                }
            ],
        )


class FakeWebConnector:
    def collect(self, request):
        return CollectionResult(
            source_id=request.source_id,
            connector="web_page",
            rows=[
                {
                    "source_id": request.source_id,
                    "connector": "web_page",
                    "title": "Memory market checks",
                    "url": "https://example.com/memory",
                    "publisher": "Example",
                    "text": (
                        "Contract prices, ASP, and revenue are rising QoQ. "
                        "AI infrastructure HBM demand and data center compute capacity are strong. "
                        "Tight supply and capacity constraints remain visible."
                    ),
                }
            ],
        )


class CrashingWebConnector:
    def collect(self, request):
        raise TimeoutError("simulated read timeout")


class StatefulManualConnector:
    connector_id = "manual"

    def collect(self, request):
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=[
                {
                    "source_id": request.source_id,
                    "connector": self.connector_id,
                    "title": "manual row",
                    "text": "manual evidence row",
                }
            ],
        )


def test_runner_dry_run_writes_plan_artifacts(tmp_path):
    engine = ResearchEngine(output_dir=tmp_path)

    result = engine.run(
        "DRAM HBM shortage",
        dry_run=True,
        run_date="2026-06-21",
        slug="memory-dry-run",
    )

    run_dir = tmp_path / "2026-06-21-memory-dry-run"
    assert result.pack_id == "memory_cycle"
    assert result.raw_rows == 0
    assert json.loads((run_dir / "run_manifest.json").read_text())["status"] == "planned"
    assert json.loads((run_dir / "query_plan.json").read_text())["pack"]["id"] == "memory_cycle"


def test_runner_marks_non_dry_run_without_sources_as_failed_no_sources(tmp_path):
    engine = ResearchEngine(output_dir=tmp_path)

    result = engine.run(
        "restaurant lease negotiation",
        run_date="2026-06-21",
        slug="generic-empty",
    )

    manifest = json.loads((tmp_path / "2026-06-21-generic-empty/run_manifest.json").read_text())
    assert result.status == "failed_no_sources"
    assert result.raw_rows == 0
    assert manifest["status"] == "failed_no_sources"
    assert "no executable sources" in " ".join(result.warnings)


def test_runner_collects_with_injected_connectors_and_writes_synthesis(tmp_path):
    engine = ResearchEngine(
        output_dir=tmp_path,
        connectors={
            "finance_quote": FakeFinanceConnector,
            "web_page": FakeWebConnector,
        },
    )

    result = engine.run(
        "DRAM HBM shortage",
        run_date="2026-06-21",
        slug="memory-collect",
    )

    run_dir = tmp_path / "2026-06-21-memory-collect"
    assert result.raw_rows == 2
    assert json.loads((run_dir / "claim_review.json").read_text())["overall"]["stance"] == "supported"
    assert json.loads((run_dir / "evidence_quality.json").read_text())["row_count"] == 2
    first_row = json.loads((run_dir / "evidence.jsonl").read_text().splitlines()[0])
    assert first_row["quality_tier"] in {"medium", "high"}
    assert (run_dir / "research_report.md").read_text().startswith("# Research Report")


def test_cli_run_subcommand_accepts_pack_auto(tmp_path, capsys):
    exit_code = main(
        [
            "run",
            "DRAM HBM shortage",
            "--pack",
            "auto",
            "--dry-run",
            "--output",
            str(tmp_path),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["pack_id"] == "memory_cycle"
    assert (tmp_path / payload["run_id"] / "query_plan.json").exists()


def test_runner_preserves_artifacts_when_connector_crashes(tmp_path):
    engine = ResearchEngine(
        output_dir=tmp_path,
        connectors={
            "finance_quote": FakeFinanceConnector,
            "web_page": CrashingWebConnector,
        },
    )

    result = engine.run(
        "DRAM HBM shortage",
        run_date="2026-06-21",
        slug="connector-crash",
    )

    run_dir = tmp_path / "2026-06-21-connector-crash"
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    rows = [json.loads(line) for line in (run_dir / "evidence.jsonl").read_text().splitlines()]

    assert result.raw_rows == 1
    assert "web_page connector crashed" in " ".join(result.warnings)
    assert manifest["warnings"] == result.warnings
    assert rows[0]["connector"] == "finance_quote"


def test_runner_accepts_connector_instances(tmp_path):
    pack_dir = tmp_path / "packs"
    pack_dir.mkdir()
    (pack_dir / "generic.json").write_text(
        json.dumps(
            {
                "id": "generic",
                "label": "Generic",
                "sources": [
                    {
                        "source_id": "manual_rows",
                        "connector": "manual",
                        "rows": [{"title": "ignored by stateful connector"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    engine = ResearchEngine(
        output_dir=tmp_path / "runs",
        pack_dir=pack_dir,
        connectors={"manual": StatefulManualConnector()},
    )

    result = engine.run("unmatched generic topic", run_date="2026-06-21", slug="instance")

    assert result.status == "complete"
    assert result.raw_rows == 1


def test_cli_imports_external_evidence_jsonl(tmp_path, capsys):
    evidence_path = tmp_path / "external.jsonl"
    evidence_path.write_text(
        json.dumps(
            {
                "title": "Lenny memory discussion",
                "url": "https://www.lennysnewsletter.com/p/memory",
                "text": "Subscriber-visible notes say HBM supply remains tight.",
                "metadata": {"platform": "lenny"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "run",
            "restaurant lease negotiation",
            "--pack",
            "auto",
            "--output",
            str(tmp_path / "runs"),
            "--external-evidence",
            str(evidence_path),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    run_dir = tmp_path / "runs" / payload["run_id"]

    assert exit_code == 0
    assert payload["status"] == "complete"
    assert payload["raw_rows"] == 1
    query_plan = json.loads((run_dir / "query_plan.json").read_text())
    execution = json.loads((run_dir / "collection_execution.json").read_text())
    row = json.loads((run_dir / "evidence.jsonl").read_text().splitlines()[0])
    assert query_plan["collection_modes"]["external_evidence"] is True
    assert execution["status_counts"] == {"ok": 1}
    assert row["connector"] == "external_jsonl"
    assert row["quality_tier"] in {"medium", "high"}
