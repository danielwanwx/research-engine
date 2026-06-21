import json

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
    assert (run_dir / "research_report.md").read_text().startswith("# Research Report")
