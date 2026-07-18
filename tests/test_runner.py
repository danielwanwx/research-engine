import json
from pathlib import Path

import pytest

from research_engine.browser_auth import ConsentStore
from research_engine.cli import main
from research_engine.connectors.authenticated_browser import AuthenticatedBrowserConnector
from research_engine.models import CollectionResult
from research_engine.packs import select_research_pack
from research_engine.platforms import build_platform_research_plan, pack_platforms_for_depth
from research_engine.runner import (
    ResearchEngine,
    apply_auth_coverage_confidence_ceiling,
    build_analysis_rows,
    build_authenticated_browser_requests,
    build_evidence_chunks,
    build_source_requests,
    normalize_rows,
)
from research_engine.synthesis import build_claim_review


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


class FakeAuthenticatedBrowserConnector:
    connector_id = "authenticated_browser"

    def collect(self, request):
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=[
                {
                    "title": "LinkedIn agent discussion",
                    "url": "https://www.linkedin.com/posts/example",
                    "text": "Agent engineering discussion with concrete deployment evidence.",
                    "content_valid": True,
                    "access_mode": "user_consented_browser",
                }
            ],
            metadata={
                "status": "ready",
                "auth_challenges": [
                    {
                        "challenge_id": "fixture-linkedin",
                        "recipe_id": "linkedin",
                        "recipe_version": 1,
                        "origin": "https://www.linkedin.com",
                        "requested_url": "https://www.linkedin.com/search/results/content/",
                        "reason": "explicit_platform_request",
                        "status": "completed",
                        "human_action_required": False,
                        "consent_required": True,
                        "created_at": "2026-07-17T00:00:00+00:00",
                    }
                ],
            },
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


class FakeDiscoveryConnector:
    connector_id = "web_search"

    def collect(self, request):
        facet_id = str(request.source.get("facet_id") or "overview")
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=[
                {
                    "source_id": request.source_id,
                    "connector": self.connector_id,
                    "title": "JSON Canvas specification",
                    "url": f"https://jsoncanvas.org/spec/{facet_id}/",
                    "text": "Search snippet must remain discovery only.",
                    "source_class": "discovery_only",
                    "source_kind": "web_search_result",
                    "query_id": request.source.get("query_id"),
                    "facet_id": request.source.get("facet_id"),
                    "claim_eligible": False,
                }
            ],
        )


class FakeCanonicalConnector:
    connector_id = "web_page"

    def collect(self, request):
        rows = []
        for page in request.source.get("pages") or []:
            rows.append(
                {
                    "source_id": request.source_id,
                    "connector": self.connector_id,
                    "title": page["title"],
                    "url": page["url"],
                    "final_url": page["url"],
                    "text": (
                        "JSON Canvas is an open file format with nodes and edges. "
                        "The canonical specification defines interoperable node, edge, color, "
                        "and metadata fields for portable infinite-canvas documents."
                    ),
                    "source_kind": "canonical_web_page",
                    "query_id": page.get("query_id"),
                    "facet_id": page.get("facet_id"),
                    "discovery_source_id": page.get("discovery_source_id"),
                    "content_valid": True,
                    "published_at": "2020-01-01",
                    "content_blocks": [
                        {"heading": "Specification", "text": (
                            "JSON Canvas defines portable nodes and edges for interoperable "
                            "infinite canvas documents."
                        )}
                    ],
                    "tables": [[[
                        "Field", "Meaning"
                    ], ["nodes", "Canvas nodes"]]],
                }
            )
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=rows,
        )


class RepairingDiscoveryConnector:
    connector_id = "web_search"

    def collect(self, request):
        if request.source.get("pass_id") == "pass-1":
            return CollectionResult(
                source_id=request.source_id,
                connector=self.connector_id,
                rows=[],
            )
        return FakeDiscoveryConnector().collect(request)


class FakeScopedJobConnector:
    connector_id = "official_job_discovery"

    def collect(self, request):
        target = request.source["target"]
        company = target["company"]
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=[
                {
                    "company": company,
                    "title": "Senior AI Engineer",
                    "role_family": "machine_learning",
                    "level": "senior",
                    "geography": "US",
                    "skills": ["Python", "distributed systems"],
                    "compensation": {"currency": "USD", "min": 200000, "max": 260000},
                    "url": f"https://{company.lower()}.example/jobs/ai-engineer",
                    "final_url": f"https://{company.lower()}.example/jobs/ai-engineer",
                    "text": (
                        "Senior AI Engineer role requiring Python and distributed systems "
                        "experience for a current United States opening."
                    ),
                    "source_kind": "official_job_posting",
                    "source_class": "official_jd",
                    "current_status": "active",
                    "is_final_page": True,
                    "content_valid": True,
                    "published_at": "2026-07-10",
                    "claim_fitness": {"disposition": "accepted", "rejection_reasons": []},
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
    assert result.pdf_report_status == "generated"
    assert result.pdf_report_path.endswith("research_report.pdf")
    assert (run_dir / "research_report.pdf").exists()
    assert json.loads((run_dir / "pdf_report_status.json").read_text())["status"] == "generated"
    assert json.loads((run_dir / "run_manifest.json").read_text())["pdf_report"][
        "status"
    ] == "generated"


def test_runner_executes_explicit_browser_recovery_and_writes_challenge_artifact(tmp_path):
    engine = ResearchEngine(
        output_dir=tmp_path,
        connectors={"authenticated_browser": FakeAuthenticatedBrowserConnector()},
    )

    result = engine.run(
        "LinkedIn agent engineering evidence",
        run_date="2026-07-17",
        search_provider="none",
    )

    run_dir = tmp_path / result.run_id
    challenges = [
        json.loads(line)
        for line in (run_dir / "auth_challenges.jsonl").read_text().splitlines()
    ]
    plan = json.loads((run_dir / "query_plan.json").read_text())
    evidence = [json.loads(line) for line in (run_dir / "evidence.jsonl").read_text().splitlines()]
    assert challenges[0]["status"] == "completed"
    assert plan["browser_auth"] == "auto"
    assert plan["auth_challenge_summary"] == {
        "total": 1,
        "completed": 1,
        "pending_human_actions": 0,
        "advisory_coverage_gaps": 0,
    }
    assert any(row["connector"] == "authenticated_browser" for row in evidence)


def test_runner_browser_auth_never_preserves_public_only_mode(tmp_path):
    engine = ResearchEngine(
        output_dir=tmp_path,
        connectors={"authenticated_browser": FakeAuthenticatedBrowserConnector()},
    )

    result = engine.run(
        "LinkedIn agent engineering evidence",
        run_date="2026-07-17",
        search_provider="none",
        browser_auth="never",
    )

    run_dir = tmp_path / result.run_id
    assert (run_dir / "auth_challenges.jsonl").read_text() == ""
    plan = json.loads((run_dir / "query_plan.json").read_text())
    assert plan["browser_auth"] == "never"
    assert plan["auth_challenge_summary"]["total"] == 0


def test_runner_noninteractive_browser_auto_stops_at_auditable_human_gate(tmp_path):
    connector = AuthenticatedBrowserConnector(
        consent_store=ConsentStore(tmp_path / "auth"),
        interactive=False,
        auth_root=tmp_path / "auth",
    )
    engine = ResearchEngine(
        output_dir=tmp_path / "runs",
        connectors={"authenticated_browser": connector},
    )

    result = engine.run(
        "LinkedIn agent engineering evidence",
        run_date="2026-07-17",
        search_provider="none",
    )

    challenge = json.loads(
        (Path(result.run_dir) / "auth_challenges.jsonl").read_text().splitlines()[0]
    )
    assert result.loop_status == "blocked"
    assert result.stop_reason == "human_action_required"
    assert challenge["status"] == "human_action_required"
    assert challenge["human_action_required"] is True


def test_cli_auth_lists_revokes_and_clears_one_profile(tmp_path, capsys):
    store = ConsentStore(tmp_path)
    store.grant(recipe_id="linkedin", recipe_version=1, origin="https://www.linkedin.com")
    profile = tmp_path / "profiles" / "linkedin"
    profile.mkdir(parents=True)
    (profile / "Preferences").write_text("fixture")

    assert main(["auth", "--root", str(tmp_path), "list", "--format", "json"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["grants"][0]["recipe_id"] == "linkedin"

    assert main(["auth", "--root", str(tmp_path), "revoke", "linkedin"]) == 0
    assert "Revoked 1" in capsys.readouterr().out
    assert main(["auth", "--root", str(tmp_path), "clear-profile", "linkedin"]) == 0
    assert "Profile cleared" in capsys.readouterr().out
    assert not profile.exists()


def test_recoverable_unknown_site_uses_origin_isolated_generic_recipe():
    blocked = CollectionResult(
        source_id="blocked",
        connector="web_page",
        rows=[
            {
                "url": "https://community.example/private/topic?token=not-an-artifact",
                "content_invalid_reasons": ["login_wall"],
                "content_valid": False,
            }
        ],
    )

    requests = build_authenticated_browser_requests(
        [blocked],
        platform_plan=[],
        topic="community evidence",
        run_date="2026-07-17",
        depth="quick",
        max_results=3,
        browser_auth="auto",
        pack_platforms=set(),
    )

    assert len(requests) == 1
    assert requests[0].source["recipe_id"] == "generic"


def test_late_document_chunks_participate_in_claim_synthesis():
    parent = {
        "evidence_id": "ev-parent",
        "connector": "web_page",
        "title": "Long report",
        "url": "https://independent.example/report",
        "text": "opening material " * 250,
        "content_blocks": [
            {"heading": "Overview", "text": "opening material " * 250},
            {"heading": "Findings", "text": "late decisive signal confirmed"},
        ],
        "content_valid": True,
        "claim_eligible": True,
    }
    chunks = build_evidence_chunks([parent])
    analysis_rows = build_analysis_rows([parent], chunks)
    pack = {
        "id": "chunk-test",
        "claim_specs": [
            {
                "claim_id": "late-signal",
                "question": "Was the late signal found?",
                "keywords": ["late decisive signal"],
                "min_evidence": 1,
                "min_independent_support": 1,
            }
        ],
        "decision_rules": {
            "supported_claims_for_supported": 1,
            "supported_claims_for_high_confidence": 1,
        },
    }

    review = build_claim_review(
        topic="late signal",
        pack=pack,
        rows=analysis_rows,
        warnings=[],
    )

    assert all(row["evidence_id"] != "ev-parent" for row in analysis_rows)
    assert any("late decisive signal" in row["text"] for row in analysis_rows)
    assert review["claims"][0]["verdict"] == "supported"
    assert review["claims"][0]["evidence_ids"][0].startswith("chunk-")

def test_runner_writes_bounded_m2_facet_plan_without_network(tmp_path):
    engine = ResearchEngine(output_dir=tmp_path)

    result = engine.run(
        "JSON Canvas adoption",
        dry_run=True,
        run_date="2026-07-16",
        depth="quick",
        search_provider="none",
    )

    plan = json.loads((tmp_path / result.run_id / "query_plan.json").read_text())
    assert plan["schema_version"] == "query_plan.v2"
    assert plan["profile"] == "generic"
    assert len(plan["queries"]) <= 3
    assert len({row["query_id"] for row in plan["queries"]}) == len(plan["queries"])
    assert plan["search_provider"] == "none"
    assert plan["third_party_query_boundary"] is False


def test_cli_loads_scope_file_and_records_search_boundary_and_as_of(tmp_path, capsys):
    scope_path = tmp_path / "scope.json"
    scope_path.write_text(
        json.dumps(
            {
                "schema_version": "research_scope.v1",
                "profile": "technical",
                "as_of": "2026-07-15",
                "filters": {},
            }
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "run",
                "JSON Canvas ecosystem",
                "--dry-run",
                "--output",
                str(tmp_path / "runs"),
                "--scope-file",
                str(scope_path),
                "--search-provider",
                "none",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    plan = json.loads(
        (tmp_path / "runs" / result["run_id"] / "query_plan.json").read_text()
    )

    assert plan["profile"] == "technical"
    assert plan["as_of"] == "2026-07-15"
    assert plan["search_provider"] == "none"
    assert plan["third_party_query_boundary"] is False


def test_cli_rejects_incomplete_job_market_scope(tmp_path):
    scope_path = tmp_path / "scope.json"
    scope_path.write_text(
        json.dumps(
            {
                "schema_version": "research_scope.v1",
                "profile": "job_market",
                "filters": {"geography": ["US"]},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="job_market scope requires"):
        main(
            [
                "run",
                "AI engineer hiring",
                "--dry-run",
                "--output",
                str(tmp_path / "runs"),
                "--scope-file",
                str(scope_path),
            ]
        )


def test_runner_refetches_discovery_candidates_and_reconciles_queries(tmp_path):
    engine = ResearchEngine(
        output_dir=tmp_path,
        connectors={
            "web_search": FakeDiscoveryConnector,
            "web_page": FakeCanonicalConnector,
        },
    )

    result = engine.run(
        "JSON Canvas adoption",
        run_date="2026-07-16",
        depth="quick",
        search_provider="anysearch",
    )

    run_dir = tmp_path / result.run_id
    rows = [json.loads(line) for line in (run_dir / "evidence.jsonl").read_text().splitlines()]
    plan = json.loads((run_dir / "query_plan.json").read_text())
    execution = json.loads((run_dir / "collection_execution.json").read_text())
    discovery = [row for row in rows if row.get("connector") == "web_search"]
    canonical = [row for row in rows if row.get("connector") == "web_page"]

    assert discovery and all(row["claim_eligible"] is False for row in discovery)
    assert canonical and all(row["content_valid"] is True for row in canonical)
    assert any(row["claim_eligible"] is True for row in canonical)
    assert all(row.get("discovery_source_id") for row in canonical)
    assert plan["query_reconciliation"]["planned"] == len(plan["queries"])
    assert plan["query_reconciliation"]["executed"] == len(plan["queries"])
    pass_ids = {record["pass_id"] for record in execution["requests"]}
    assert {"pass-1", "canonical-refetch"}.issubset(pass_ids)
    assert all(not pass_id.startswith("pass-3") for pass_id in pass_ids)


def test_runner_applies_freshness_windows_and_writes_chunks_and_coverage(tmp_path):
    engine = ResearchEngine(
        output_dir=tmp_path,
        connectors={
            "web_search": FakeDiscoveryConnector,
            "web_page": FakeCanonicalConnector,
        },
    )
    scope = {
        "schema_version": "research_scope.v1",
        "profile": "market_landscape",
        "as_of": "2026-07-16",
        "filters": {
            "geography": ["US"],
            "definition": ["hosted AI inference platforms"],
        },
    }

    result = engine.run(
        "AI inference serving market",
        run_date="2026-07-16",
        depth="quick",
        research_scope=scope,
        search_provider="anysearch",
    )
    run_dir = tmp_path / result.run_id
    rows = [json.loads(line) for line in (run_dir / "evidence.jsonl").read_text().splitlines()]
    chunks = [json.loads(line) for line in (run_dir / "chunks.jsonl").read_text().splitlines()]
    coverage = json.loads((run_dir / "facet_coverage.json").read_text())
    claim_review = json.loads((run_dir / "claim_review.json").read_text())
    dated = [
        row
        for row in rows
        if row.get("freshness_window_days") and row.get("connector") == "web_page"
    ]

    assert dated and all(row["freshness_status"] == "stale" for row in dated)
    assert all(row["claim_eligible"] is False for row in dated)
    assert chunks and all(chunk["parent_evidence_id"] for chunk in chunks)
    assert coverage["schema_version"] == "facet_coverage.v1"
    assert "pricing" in coverage["missing_required_facets"]
    assert claim_review["claim_context"]["geography"] == ["US"]
    assert all(claim["claim_context"] for claim in claim_review["claims"])


def test_runner_executes_exactly_one_repair_pass_and_preserves_pass_one(tmp_path):
    engine = ResearchEngine(
        output_dir=tmp_path,
        connectors={
            "web_search": RepairingDiscoveryConnector,
            "web_page": FakeCanonicalConnector,
        },
    )

    result = engine.run(
        "JSON Canvas adoption",
        run_date="2026-07-16",
        depth="quick",
        search_provider="anysearch",
    )
    run_dir = tmp_path / result.run_id
    repair = json.loads((run_dir / "repair_record.json").read_text())
    execution = json.loads((run_dir / "collection_execution.json").read_text())
    pass_ids = [record["pass_id"] for record in execution["requests"]]

    assert repair["attempted"] is True
    assert repair["pass_id"] == "pass-2"
    assert repair["trigger_count"] > 0
    assert "pass-1" in pass_ids
    assert "pass-2" in pass_ids
    assert all(not pass_id.startswith("pass-3") for pass_id in pass_ids)


def test_runner_writes_scoped_point_in_time_job_snapshot(tmp_path):
    engine = ResearchEngine(
        output_dir=tmp_path,
        connectors={"official_job_discovery": FakeScopedJobConnector},
    )
    scope = {
        "schema_version": "research_scope.v1",
        "profile": "job_market",
        "as_of": "2026-07-16",
        "filters": {
            "geography": ["US"],
            "role_terms": ["AI Engineer"],
            "levels": ["senior"],
            "companies": ["Anthropic", "OpenAI"],
        },
    }

    result = engine.run(
        "AI engineer hiring market",
        run_date="2026-07-16",
        depth="quick",
        research_scope=scope,
        search_provider="none",
    )
    run_dir = tmp_path / result.run_id
    snapshot = json.loads((run_dir / "job_market_snapshot.json").read_text())

    assert snapshot["as_of"] == "2026-07-16"
    assert snapshot["counts"]["active"] == 2
    assert snapshot["coverage"]["denominator"] == 2
    assert snapshot["coverage"]["checked_count"] == 2
    assert snapshot["trend"] is None
    assert all(opening["evidence_ids"] for opening in snapshot["openings"])


def test_runner_versions_same_run_without_mutating_first_bundle(tmp_path):
    engine = ResearchEngine(output_dir=tmp_path)

    first = engine.run("immutable rerun", dry_run=True, run_date="2026-07-16")
    first_dir = tmp_path / first.run_id
    first_bundle = {
        path.name: path.read_bytes() for path in first_dir.iterdir() if path.is_file()
    }

    second = engine.run("immutable rerun", dry_run=True, run_date="2026-07-16")

    assert first.run_id == "2026-07-16-immutable-rerun"
    assert second.run_id == "2026-07-16-immutable-rerun--02"
    assert (tmp_path / second.run_id / "run_manifest.json").exists()
    assert {
        path.name: path.read_bytes() for path in first_dir.iterdir() if path.is_file()
    } == first_bundle


def test_normalize_rows_assigns_unique_ids_and_preserves_source_ids():
    results = [
        CollectionResult(
            source_id="external",
            connector="external_jsonl",
            rows=[
                {"evidence_id": "ev-0001", "title": "first"},
                {"evidence_id": "ev-0001", "title": "second"},
            ],
        ),
        CollectionResult(
            source_id="web",
            connector="web_page",
            rows=[{"evidence_id": "ev-0001", "title": "third"}],
        ),
    ]

    rows = normalize_rows(results)

    assert [row["evidence_id"] for row in rows] == ["ev-0001", "ev-0002", "ev-0003"]
    assert [row["source_evidence_id"] for row in rows] == ["ev-0001"] * 3


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


def test_pdf_failure_is_disclosed_without_changing_research_status(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "research_engine.runner.render_pdf_report",
        lambda _run_dir: {
            "schema_version": "pdf_report_status.v1",
            "status": "failed",
            "path": "research_report.pdf",
            "error_type": "RuntimeError",
            "error_message": "simulated renderer failure",
        },
    )
    engine = ResearchEngine(output_dir=tmp_path)

    result = engine.run(
        "restaurant lease negotiation",
        run_date="2026-06-21",
        slug="pdf-failure",
    )

    run_dir = tmp_path / "2026-06-21-pdf-failure"
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    assert result.status == "failed_no_sources"
    assert result.pdf_report_status == "failed"
    assert manifest["status"] == "failed_no_sources"
    assert manifest["pdf_report"]["status"] == "failed"
    assert "PDF report generation failed" in " ".join(result.warnings)


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


def test_job_market_deep_run_schedules_advisory_linkedin_but_quick_does_not():
    topic = "US software engineer employment market"
    pack = select_research_pack(topic)

    def browser_requests(depth):
        platform_plan = build_platform_research_plan(
            topic,
            scope="broad",
            pack=pack,
            depth=depth,
        )
        return build_authenticated_browser_requests(
            [],
            platform_plan=platform_plan,
            topic=topic,
            run_date="2026-07-17",
            depth=depth,
            max_results=3,
            browser_auth="auto",
            pack_platforms=pack_platforms_for_depth(pack, depth),
        )

    assert browser_requests("quick") == []
    deep_requests = browser_requests("deep")
    assert len(deep_requests) == 1
    assert deep_requests[0].source["recipe_id"] == "linkedin"
    assert deep_requests[0].source["auth_gate_policy"] == "advisory"
    assert deep_requests[0].source["challenge_reason"] == "pack_platform_priority"


def test_missing_advisory_linkedin_coverage_caps_claim_confidence():
    review = {"overall": {"confidence": "high", "risk_flags": []}}

    apply_auth_coverage_confidence_ceiling(
        review,
        [
            {
                "recipe_id": "linkedin",
                "coverage_missing": True,
                "blocking": False,
            }
        ],
    )

    assert review["overall"]["confidence"] == "medium"
    assert review["overall"]["confidence_ceiling"] == "medium"
    assert review["overall"]["risk_flags"] == ["linkedin_coverage_missing"]


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
    claim_review = json.loads((run_dir / "claim_review.json").read_text())
    assert claim_review["overall"]["stance"] == "needs_more_evidence"
    assert claim_review["overall"]["confidence"] == "low"
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
            "--search-provider",
            "none",
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
            "--search-provider",
            "none",
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
            "--search-provider",
            "none",
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


def test_cli_journal_records_distinct_reruns_and_redacts_argv(tmp_path, capsys):
    output_dir = tmp_path / "runs"
    argv = [
        "run",
        "journal rerun",
        "--output",
        str(output_dir),
        "--dry-run",
        "--agent-reach-command",
        (
            "fake client_secret=smoke-secret --token split-secret "
            '--client-secret compound-flag-secret "{query}"'
        ),
        "--agent-reach-command",
        'fake aws_secret_access_key=journal-aws-secret "{query}"',
    ]

    assert main(argv) == 0
    first = json.loads(capsys.readouterr().out)
    assert main(argv) == 0
    second = json.loads(capsys.readouterr().out)
    journal = [
        json.loads(line)
        for line in (output_dir / "journal.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert [entry["exit_status"] for entry in journal] == [0, 0]
    assert [entry["run_id"] for entry in journal] == [first["run_id"], second["run_id"]]
    assert first["run_id"] != second["run_id"]
    assert journal[0]["started_at"] <= journal[1]["started_at"]
    assert all(entry["started_at"] <= entry["ended_at"] for entry in journal)
    journal_text = (output_dir / "journal.jsonl").read_text()
    assert "smoke-secret" not in journal_text
    assert "split-secret" not in journal_text
    assert "compound-flag-secret" not in journal_text
    assert "journal-aws-secret" not in journal_text


def test_cli_journal_records_engine_failure(tmp_path, monkeypatch):
    output_dir = tmp_path / "runs"

    def fail_run(self, topic, **kwargs):
        raise RuntimeError(
            "RuntimeError: client_secret=journal-client-failure "
            "request failed: aws_secret_access_key=journal-aws-failure "
            "embedded Authorization: Basic am91cm5hbDpzZWNyZXQ="
        )

    monkeypatch.setattr(ResearchEngine, "run", fail_run)

    with pytest.raises(RuntimeError, match="client_secret"):
        main(["run", "failed journal", "--output", str(output_dir)])

    entry = json.loads((output_dir / "journal.jsonl").read_text(encoding="utf-8"))
    assert entry["exit_status"] == 1
    assert entry["run_id"] is None
    assert entry["run_dir"] is None
    assert entry["error_type"] == "RuntimeError"
    assert "journal-client-failure" not in json.dumps(entry)
    assert "journal-aws-failure" not in json.dumps(entry)
    assert "am91cm5hbDpzZWNyZXQ=" not in json.dumps(entry)


def test_cli_does_not_print_success_before_journal_append(tmp_path, monkeypatch, capsys):
    def fail_journal(**kwargs):
        raise OSError("simulated journal failure")

    monkeypatch.setattr("research_engine.cli.append_invocation_record", fail_journal)

    with pytest.raises(OSError, match="simulated journal failure"):
        main(["run", "journal failure", "--dry-run", "--output", str(tmp_path / "runs")])

    assert capsys.readouterr().out == ""
