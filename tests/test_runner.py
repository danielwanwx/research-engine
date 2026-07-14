import json

from research_engine.cli import main
from research_engine.models import CollectionResult
from research_engine.platforms import build_platform_research_plan
from research_engine.runner import ResearchEngine, build_source_requests


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


class FakeAgentReachConnector:
    connector_id = "agent_reach_bridge"

    def collect(self, request):
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=[
                {
                    "source_id": request.source_id,
                    "connector": self.connector_id,
                    "platform": "reddit",
                    "title": "Forum memory cycle check",
                    "url": "https://www.reddit.com/r/stocks/comments/example",
                    "text": "Forum discussion says HBM tight supply remains a concern.",
                    "source_kind": "agent_reach_result",
                    "access_mode": "agent_reach_upstream_cli",
                }
            ],
        )


class FakeOpenCliConnector:
    connector_id = "opencli_bridge"

    def collect(self, request):
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=[
                {
                    "source_id": request.source_id,
                    "connector": self.connector_id,
                    "platform": "x",
                    "title": "Loop engineering seed",
                    "url": "https://x.com/example/status/1",
                    "text": "Harness layer and verifier loop discussion.",
                    "source_kind": "opencli_result",
                    "access_mode": "opencli_upstream_cli",
                }
            ],
        )


class FakeGitHubPublicConnector:
    connector_id = "github_public_search"

    def collect(self, request):
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=[
                {
                    "source_id": request.source_id,
                    "connector": self.connector_id,
                    "platform": "github",
                    "title": "example/loopx",
                    "url": "https://github.com/example/loopx",
                    "text": "Loop engineering for long-running AI agents.",
                    "source_kind": "github_public_repository",
                    "access_mode": "public_github_api",
                }
            ],
        )


class EmptyManualConnector:
    connector_id = "manual"

    def collect(self, request):
        return CollectionResult(source_id=request.source_id, connector=self.connector_id, rows=[])


class SensitiveStringConnector:
    connector_id = "manual"

    def collect(self, request):
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=[
                {
                    "source_id": request.source_id,
                    "connector": self.connector_id,
                    "title": "unsafe custom connector row",
                    "text": "Visible policy text Cookie: sessionid=custom-secret-session",
                    "metadata": {"authorization": "Bearer custom-secret-token"},
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
    query_plan = json.loads((run_dir / "query_plan.json").read_text())
    loop_contract = json.loads((run_dir / "loop_contract.json").read_text())
    loop_record = json.loads((run_dir / "loop_record.json").read_text())
    assert query_plan["pack"]["id"] == "memory_cycle"
    assert {"x", "reddit", "github"}.issubset(
        {row["platform"] for row in query_plan["platform_research_plan"]}
    )
    assert loop_contract["loop_id"] == "research_loop_v1"
    assert loop_record["loop_status"] == "planned"
    assert loop_record["stop_reason"] == "planned_before_collection"
    assert result.loop_status == "planned"
    assert result.stop_reason == "planned_before_collection"


def test_runner_marks_non_dry_run_without_sources_as_failed_no_sources(tmp_path):
    engine = ResearchEngine(output_dir=tmp_path)

    result = engine.run(
        "restaurant lease negotiation",
        run_date="2026-06-21",
        slug="generic-empty",
    )

    manifest = json.loads((tmp_path / "2026-06-21-generic-empty/run_manifest.json").read_text())
    loop_record = json.loads((tmp_path / "2026-06-21-generic-empty/loop_record.json").read_text())
    assert result.status == "failed_no_sources"
    assert result.loop_status == "blocked"
    assert result.stop_reason == "no_executable_sources"
    assert result.raw_rows == 0
    assert manifest["status"] == "failed_no_sources"
    assert manifest["loop_summary"]["loop_status"] == "blocked"
    assert loop_record["stop_reason"] == "no_executable_sources"
    assert any(
        action["reason"] == "failed_no_sources" for action in loop_record["feedback_actions"]
    )
    assert "no executable sources" in " ".join(result.warnings)


def test_build_source_requests_can_add_public_platform_search_pages():
    pack = {"id": "generic", "sources": []}
    platform_plan = build_platform_research_plan(
        "OpenAI backend engineer interview loop",
        scope="all",
        pack=pack,
    )

    default_requests = build_source_requests(
        pack,
        topic="OpenAI backend engineer interview loop",
        platform_plan=platform_plan,
    )
    search_requests = build_source_requests(
        pack,
        topic="OpenAI backend engineer interview loop",
        platform_plan=platform_plan,
        web_search_pages=True,
    )

    assert not default_requests
    source_ids = {request.source_id for request in search_requests}
    assert "platform_search_pages" in source_ids
    search_source = next(request.source for request in search_requests if request.source_id == "platform_search_pages")
    assert search_source["connector"] == "web_page"
    assert search_source["source_kind"] == "platform_search_page"
    page_publishers = {page["publisher"] for page in search_source["pages"]}
    assert {"Reddit", "Hacker News"}.issubset(page_publishers)


def test_runner_marks_empty_connector_results_as_failed_no_rows(tmp_path):
    pack_dir = tmp_path / "packs"
    pack_dir.mkdir()
    (pack_dir / "generic.json").write_text(
        json.dumps(
            {
                "id": "generic",
                "label": "Generic",
                "sources": [{"source_id": "empty_rows", "connector": "manual"}],
            }
        ),
        encoding="utf-8",
    )
    engine = ResearchEngine(
        output_dir=tmp_path / "runs",
        pack_dir=pack_dir,
        connectors={"manual": EmptyManualConnector},
    )

    result = engine.run("empty connector result", run_date="2026-06-27", slug="empty")

    run_dir = tmp_path / "runs/2026-06-27-empty"
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    loop_record = json.loads((run_dir / "loop_record.json").read_text())

    assert result.status == "failed_no_rows"
    assert result.loop_status == "blocked"
    assert result.stop_reason == "sources_returned_no_evidence"
    assert manifest["status"] == "failed_no_rows"
    assert loop_record["loop_status"] == "blocked"
    assert loop_record["stop_reason"] == "sources_returned_no_evidence"


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
    assert (
        json.loads((run_dir / "claim_review.json").read_text())["overall"]["stance"] == "supported"
    )
    assert json.loads((run_dir / "evidence_quality.json").read_text())["row_count"] == 2
    loop_record = json.loads((run_dir / "loop_record.json").read_text())
    first_row = json.loads((run_dir / "evidence.jsonl").read_text().splitlines()[0])
    assert first_row["quality_tier"] in {"medium", "high"}
    assert loop_record["loop_status"] in {"complete", "complete_with_review_required"}
    assert {check["check_id"] for check in loop_record["check_results"]}.issuperset(
        {"bounded_execution", "evidence_collected", "claim_grounding"}
    )
    assert (run_dir / "research_report.md").read_text().startswith("# Research Report")
    assert "## Loop Status" in (run_dir / "research_report.md").read_text()


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
    assert payload["run_status"] == "planned"
    assert payload["loop_status"] == "planned"
    assert payload["stop_reason"] == "planned_before_collection"
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


def test_runner_sanitizes_custom_connector_rows_before_artifact_write(tmp_path):
    pack_dir = tmp_path / "packs"
    pack_dir.mkdir()
    (pack_dir / "generic.json").write_text(
        json.dumps(
            {
                "id": "generic",
                "label": "Generic",
                "sources": [{"source_id": "unsafe_rows", "connector": "manual"}],
            }
        ),
        encoding="utf-8",
    )
    engine = ResearchEngine(
        output_dir=tmp_path / "runs",
        pack_dir=pack_dir,
        connectors={"manual": SensitiveStringConnector},
        source_timeout_seconds=10,
    )

    result = engine.run("custom connector sensitive row", run_date="2026-06-27", slug="safe")

    run_dir = tmp_path / "runs/2026-06-27-safe"
    artifact_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            run_dir / "run_manifest.json",
            run_dir / "evidence.jsonl",
            run_dir / "loop_record.json",
            run_dir / "research_report.md",
        )
    )
    row = json.loads((run_dir / "evidence.jsonl").read_text().splitlines()[0])

    assert result.status == "complete_with_warnings"
    assert result.loop_status == "complete_with_review_required"
    assert "artifact sanitation redacted/dropped sensitive field" in " ".join(result.warnings)
    assert "custom-secret-session" not in artifact_text
    assert "custom-secret-token" not in artifact_text
    assert "authorization" not in row["metadata"]
    assert "[REDACTED]" in row["text"]


def test_runner_collects_agent_reach_bridge_with_injected_connector(tmp_path):
    engine = ResearchEngine(
        output_dir=tmp_path,
        connectors={"agent_reach_bridge": FakeAgentReachConnector},
    )

    result = engine.run(
        "restaurant lease negotiation",
        run_date="2026-06-21",
        slug="agent-reach",
        agent_reach=True,
        platform_scope="deep",
        agent_reach_command_templates=['fake-search "{query}" --platform {platform}'],
    )

    run_dir = tmp_path / "2026-06-21-agent-reach"
    query_plan = json.loads((run_dir / "query_plan.json").read_text())
    execution = json.loads((run_dir / "collection_execution.json").read_text())
    row = json.loads((run_dir / "evidence.jsonl").read_text().splitlines()[0])

    assert result.status == "complete"
    assert result.raw_rows == 1
    assert query_plan["platform_scope"] == "deep"
    assert query_plan["collection_modes"]["agent_reach"] is True
    assert query_plan["agent_reach_commands"] == ['fake-search "{query}" --platform {platform}']
    assert "agent_reach_bridge" in {source["source_id"] for source in query_plan["sources"]}
    assert execution["status_counts"] == {"ok": 1}
    assert row["connector"] == "agent_reach_bridge"
    assert row["quality_tier"] in {"medium", "high"}


def test_runner_collects_opencli_bridge_from_pack_source(tmp_path):
    pack_dir = tmp_path / "packs"
    pack_dir.mkdir()
    (pack_dir / "generic.json").write_text(
        json.dumps(
            {
                "id": "generic",
                "label": "Generic",
                "sources": [
                    {
                        "source_id": "opencli_loop_seed",
                        "connector": "opencli_bridge",
                        "platform": "x",
                        "query": "loop engineering",
                        "command": 'opencli x search --query "{query}" --format json',
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    engine = ResearchEngine(
        output_dir=tmp_path / "runs",
        pack_dir=pack_dir,
        connectors={"opencli_bridge": FakeOpenCliConnector},
    )

    result = engine.run("loop engineering", run_date="2026-06-26", slug="opencli")

    run_dir = tmp_path / "runs/2026-06-26-opencli"
    query_plan = json.loads((run_dir / "query_plan.json").read_text())
    row = json.loads((run_dir / "evidence.jsonl").read_text().splitlines()[0])

    assert result.status == "complete"
    assert query_plan["collection_modes"]["opencli"] is True
    assert query_plan["sources"][0]["connector"] == "opencli_bridge"
    assert row["connector"] == "opencli_bridge"
    assert row["platform"] == "x"


def test_runner_adds_github_public_fallback_from_platform_plan(tmp_path):
    engine = ResearchEngine(
        output_dir=tmp_path / "runs",
        connectors={"github_public_search": FakeGitHubPublicConnector},
    )

    result = engine.run(
        "#loop engineering",
        run_date="2026-06-27",
        slug="loop-engineering",
        platform_scope="all",
    )

    run_dir = tmp_path / "runs/2026-06-27-loop-engineering"
    query_plan = json.loads((run_dir / "query_plan.json").read_text())
    row = json.loads((run_dir / "evidence.jsonl").read_text().splitlines()[0])

    assert result.status == "complete"
    assert query_plan["collection_modes"]["github_public"] is True
    assert "github_public_search" in {source["source_id"] for source in query_plan["sources"]}
    assert row["connector"] == "github_public_search"
    assert row["platform"] == "github"


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
    assert payload["run_status"] == "complete"
    assert payload["loop_status"] == "complete_with_review_required"
    assert payload["stop_reason"] == "completed_with_review_required"
    assert payload["raw_rows"] == 1
    query_plan = json.loads((run_dir / "query_plan.json").read_text())
    execution = json.loads((run_dir / "collection_execution.json").read_text())
    row = json.loads((run_dir / "evidence.jsonl").read_text().splitlines()[0])
    assert query_plan["collection_modes"]["external_evidence"] is True
    assert query_plan["external_evidence_paths"][0]["name"] == "external.jsonl"
    assert "path_hash" in query_plan["external_evidence_paths"][0]
    assert execution["status_counts"] == {"ok": 1}
    assert row["connector"] == "external_jsonl"
    assert row["quality_tier"] in {"medium", "high"}


def test_cli_external_evidence_redacts_secrets_from_artifacts(tmp_path, capsys):
    evidence_path = tmp_path / "external.jsonl"
    evidence_path.write_text(
        json.dumps(
            {
                "title": "Visible source",
                "url": "https://example.com/source",
                "text": "Visible evidence token=artifact-secret-token",
                "cookie": "artifact-secret-cookie",
                "metadata": {"platform": "x", "authorization": "Bearer artifact-secret-token"},
                "metrics": {"views": 10, "api_key": "artifact-secret-key"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "run",
            "artifact redaction check",
            "--pack",
            "auto",
            "--output",
            str(tmp_path / "runs"),
            "--external-evidence",
            str(evidence_path),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    run_dir = tmp_path / "runs" / payload["run_id"]
    artifact_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            run_dir / "run_manifest.json",
            run_dir / "query_plan.json",
            run_dir / "collection_execution.json",
            run_dir / "evidence.jsonl",
            run_dir / "research_report.md",
        )
    )

    assert exit_code == 0
    assert payload["status"] == "complete_with_warnings"
    assert payload["loop_status"] == "complete_with_review_required"
    assert "artifact-secret-token" not in artifact_text
    assert "artifact-secret-cookie" not in artifact_text
    assert "artifact-secret-key" not in artifact_text
    assert str(evidence_path.parent) not in artifact_text


def test_cli_external_evidence_directory_warning_does_not_leak_full_path(tmp_path, capsys):
    evidence_path = tmp_path / "external_dir.jsonl"
    evidence_path.mkdir()

    exit_code = main(
        [
            "run",
            "external evidence path leak",
            "--pack",
            "auto",
            "--output",
            str(tmp_path / "runs"),
            "--external-evidence",
            str(evidence_path),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    run_dir = tmp_path / "runs" / payload["run_id"]
    artifact_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            run_dir / "run_manifest.json",
            run_dir / "collection_execution.json",
            run_dir / "research_report.md",
        )
    )

    assert exit_code == 0
    assert payload["status"] == "failed_no_rows"
    assert "external_dir.jsonl#" in artifact_text
    assert str(evidence_path.parent) not in artifact_text
    assert "connector crashed" not in artifact_text


def test_cli_dry_run_records_platform_scope_and_agent_reach(tmp_path, capsys):
    exit_code = main(
        [
            "run",
            "cross platform forum research",
            "--output",
            str(tmp_path / "runs"),
            "--dry-run",
            "--platform-scope",
            "all",
            "--agent-reach",
            "--agent-reach-command",
            'fake-search "{query}" --platform {platform}',
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    query_plan = json.loads((tmp_path / "runs" / payload["run_id"] / "query_plan.json").read_text())
    platforms = {row["platform"] for row in query_plan["platform_research_plan"]}

    assert exit_code == 0
    assert query_plan["platform_scope"] == "all"
    assert query_plan["collection_modes"]["agent_reach"] is True
    assert query_plan["agent_reach_commands"] == ['fake-search "{query}" --platform {platform}']
    assert {"x", "reddit", "bilibili", "xueqiu"}.issubset(platforms)


def test_cli_dry_run_redacts_agent_reach_command_templates(tmp_path, capsys):
    exit_code = main(
        [
            "run",
            "command redaction",
            "--output",
            str(tmp_path / "runs"),
            "--dry-run",
            "--agent-reach",
            "--agent-reach-command",
            'fake-search --token dry-run-secret-token "{query}"',
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    query_plan = json.loads((tmp_path / "runs" / payload["run_id"] / "query_plan.json").read_text())

    assert exit_code == 0
    assert "dry-run-secret-token" not in json.dumps(query_plan)
    assert query_plan["agent_reach_commands"] == ['fake-search --token [REDACTED] "{query}"']
