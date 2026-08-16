"""Minimal offline regression evaluation for Research Engine."""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
from typing import Any

from research_engine.cli import main as cli_main
from research_engine.connectors.web import WebPageConnector, fetch_page_result
from research_engine.conflicts import build_claim_chains
from research_engine.extraction import extract_content
from research_engine.freshness import enrich_row_freshness
from research_engine.job_market import build_job_market_snapshot
from research_engine.models import CollectionRequest, CollectionResult, utc_now
from research_engine.quality import enrich_rows_with_quality
from research_engine.relevance import rank_github_repositories
from research_engine.runner import ResearchEngine
from research_engine.synthesis import build_claim_review, build_supply_demand_matrix


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE = REPO_ROOT / "evals" / "fixtures" / "adversarial_rows.json"
DEFAULT_V2_FIXTURE = REPO_ROOT / "evals" / "fixtures" / "benchmarks.json"


class _OfflineResponse:
    def __init__(self, case: dict[str, Any]) -> None:
        self.body = str(case.get("body") or "").encode("utf-8")
        self.url = str(case["url"])
        self.status = int(case.get("status") or 200)
        self.headers = {"content-type": str(case.get("content_type") or "text/html")}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, limit: int) -> bytes:
        return self.body[:limit]

    def geturl(self) -> str:
        return self.url


class _OfflineOpener:
    def __init__(self, response: _OfflineResponse) -> None:
        self.response = response

    def open(self, request, timeout):
        return self.response


class _FixtureGitHubConnector:
    connector_id = "github_public_search"

    def collect(self, request: CollectionRequest) -> CollectionResult:
        query = str(request.source.get("query") or "")
        title = (
            "vllm-project/vllm"
            if "vllm" in query.lower()
            else "sgl-project/sglang"
        )
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=[
                {
                    "source_id": request.source_id,
                    "connector": self.connector_id,
                    "title": title,
                    "url": f"https://github.com/{title}",
                    "text": f"{title} canonical inference engine repository",
                    "query_id": request.source.get("query_id"),
                    "facet_id": request.source.get("facet_id"),
                    "source_kind": "github_public_repository",
                    "license_spdx": "Apache-2.0",
                    "pushed_at": "2026-07-10T00:00:00Z",
                    "updated_at": "2026-07-10T00:00:00Z",
                    "default_branch": "main",
                    "topics": ["llm", "inference"],
                    "metrics": {"stars": 1000, "forks": 100, "open_issues": 10},
                }
            ],
            metadata={"status": "ready"},
        )


class _FixtureDiscoveryConnector:
    connector_id = "web_search"

    def __init__(
        self,
        results: list[dict[str, Any]] | None = None,
        *,
        empty_first_facets: set[str] | None = None,
    ) -> None:
        self.results = results
        self.empty_first_facets = set(empty_first_facets or set())

    def collect(self, request: CollectionRequest) -> CollectionResult:
        facet_id = str(request.source.get("facet_id") or "overview")
        query_id = str(request.source.get("query_id") or "")
        if (
            request.source.get("pass_id") == "pass-1"
            and facet_id in self.empty_first_facets
        ):
            return CollectionResult(
                source_id=request.source_id,
                connector=self.connector_id,
                rows=[],
                metadata={"status": "empty", "provider": "fixture"},
            )
        candidates = self.results or [
            {
                "title": f"{facet_id} official evidence",
                "url": f"https://fixture-{facet_id}.example/report",
                "snippet": str(request.source.get("query") or request.topic),
            }
        ]
        rows = [
            {
                "source_id": request.source_id,
                "connector": self.connector_id,
                "title": str(candidate["title"]),
                "url": str(candidate["url"]),
                "text": str(candidate.get("snippet") or ""),
                "source_kind": "web_search_result",
                "source_class": "discovery_only",
                "claim_eligible": False,
                "query_id": query_id,
                "facet_id": facet_id,
            }
            for candidate in candidates[: request.max_results]
        ]
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=rows,
            metadata={"status": "ready", "provider": "fixture"},
        )


class _FixtureCanonicalConnector:
    connector_id = "web_page"

    def collect(self, request: CollectionRequest) -> CollectionResult:
        rows: list[dict[str, Any]] = []
        for page in list(request.source.get("pages") or [])[: request.max_results]:
            facet_id = str(page.get("facet_id") or "overview")
            text = " ".join(
                value
                for value in (
                    request.topic,
                    facet_id.replace("_", " "),
                    str(page.get("title") or ""),
                    "official primary current independent evidence",
                )
                if value
            )
            rows.append(
                {
                    **{
                        key: page[key]
                        for key in (
                            "discovery_source_id",
                            "facet_id",
                            "query_id",
                            "source_class",
                            "source_kind",
                        )
                        if key in page
                    },
                    "source_id": request.source_id,
                    "connector": self.connector_id,
                    "title": str(page.get("title") or page["url"]),
                    "url": str(page["url"]),
                    "final_url": str(page["url"]),
                    "publisher": str(page.get("publisher") or "fixture publisher"),
                    "text": text[:4_000],
                    "content_blocks": [{"heading": facet_id, "text": text}],
                    "content_valid": True,
                    "is_final_page": True,
                    "published_at": "2026-07-10",
                    "content_type": "text/html",
                }
            )
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=rows,
            metadata={"status": "ready" if rows else "empty"},
        )


def _offline_connector(cases: list[dict[str, Any]]) -> WebPageConnector:
    case_by_url = {str(case["url"]): case for case in cases}

    def fetcher(url: str):
        case = case_by_url[url]
        if case.get("error"):
            raise ValueError(str(case["error"]))
        return fetch_page_result(
            url,
            opener=_OfflineOpener(_OfflineResponse(case)),
            rendered_fetcher=lambda *args, **kwargs: None,
        )

    return WebPageConnector(fetcher=fetcher)


def _evidence_ids(claims: list[dict[str, Any]], key: str = "evidence_ids") -> set[str]:
    return {
        str(evidence_id)
        for claim in claims
        for evidence_id in claim.get(key) or []
    }


def _display_fixture_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT))
    except ValueError:
        return str(resolved)


def run_eval(*, fixture_path: Path = DEFAULT_FIXTURE, output_dir: Path) -> dict[str, Any]:
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    cases = list(payload.get("cases") or [])
    case_by_url = {str(case["url"]): case for case in cases}
    connector_result = _offline_connector(cases).collect(
        CollectionRequest(
            source={
                "source_id": "offline_adversarial_pages",
                "connector": "web_page",
                "pages": [
                    {"url": case["url"], "title": case["id"], "publisher": "offline fixture"}
                    for case in cases
                ],
            },
            topic="offline evidence validity regression",
            run_date="2026-07-16",
            depth="audit",
            max_results=len(cases),
        )
    )
    rows = []
    for row in connector_result.rows:
        case = case_by_url[str(row["url"])]
        rows.append(
            {
                **row,
                "evidence_id": str(case["id"]),
                "expected_valid": bool(case["expected_valid"]),
            }
        )

    enriched, quality = enrich_rows_with_quality(
        rows,
        topic="offline evidence validity regression",
        pack={"id": "eval_validity"},
    )
    expected_by_id = {
        str(case["id"]): bool(case["expected_valid"])
        for case in cases
        if case.get("expected_row") is True
    }
    detected_by_id = {
        str(row["evidence_id"]): bool(row["content_valid"])
        for row in enriched
    }
    invalid_ids = {
        evidence_id for evidence_id, expected in expected_by_id.items() if expected is False
    }
    transport_cases = [case for case in cases if case.get("expected_row") is False]
    transport_detected = all(
        any(str(case["url"]).split("/", 3)[-1] in warning for warning in connector_result.warnings)
        for case in transport_cases
    )

    pack = {
        "id": "eval_validity",
        "profile": "eval_validity",
        "claim_specs": [
            {
                "claim_id": "research_finding",
                "question": "Is a valid research finding present?",
                "keywords": ["research finding"],
                "min_evidence": 1,
            }
        ],
        "decision_rules": {
            "supported_claims_for_supported": 1,
            "supported_or_partial_for_partial": 1,
            "supported_claims_for_high_confidence": 1,
        },
        "matrix_nodes": [
            {
                "node_id": "research_finding",
                "side": "evidence",
                "label": "Research finding",
                "keywords": ["research finding"],
                "min_evidence": 1,
            }
        ],
    }
    pack_review = build_claim_review(
        topic="offline evidence validity regression",
        pack=pack,
        rows=enriched,
        warnings=quality.get("warnings") or [],
    )
    generic_review = build_claim_review(
        topic="offline evidence validity regression",
        pack={"id": "generic", "label": "Eval", "intent": "general_research"},
        rows=enriched,
        warnings=quality.get("warnings") or [],
    )
    matrix = build_supply_demand_matrix(
        topic="offline evidence validity regression",
        pack=pack,
        rows=enriched,
    )

    pack_ids = _evidence_ids(pack_review.get("claims") or [])
    generic_ids = _evidence_ids(generic_review.get("claims") or [])
    matrix_ids = _evidence_ids(matrix.get("rows") or [])
    checks = [
        {
            "id": "connector_probe_classification",
            "passed": detected_by_id == expected_by_id,
            "expected": expected_by_id,
            "actual": detected_by_id,
        },
        {
            "id": "transport_failure_visible",
            "passed": transport_detected,
            "warnings": connector_result.warnings,
        },
        {
            "id": "invalid_count",
            "passed": quality.get("invalid_evidence_count") == len(invalid_ids),
            "expected": len(invalid_ids),
            "actual": quality.get("invalid_evidence_count"),
        },
        {
            "id": "invalid_pack_claim_refs",
            "passed": not (pack_ids & invalid_ids),
            "invalid_refs": sorted(pack_ids & invalid_ids),
        },
        {
            "id": "invalid_generic_claim_refs",
            "passed": not (generic_ids & invalid_ids),
            "invalid_refs": sorted(generic_ids & invalid_ids),
        },
        {
            "id": "invalid_matrix_refs",
            "passed": not (matrix_ids & invalid_ids),
            "invalid_refs": sorted(matrix_ids & invalid_ids),
        },
        {
            "id": "invalid_conflict_exclusion",
            "passed": quality.get("conflict_flags") == [],
            "actual": quality.get("conflict_flags"),
        },
        {
            "id": "valid_claim_survives",
            "passed": pack_ids == {"valid-html"},
            "actual": sorted(pack_ids),
        },
        {
            "id": "observability",
            "passed": len(enriched) == sum(1 for case in cases if case.get("expected_row")),
            "expected_rows": sum(1 for case in cases if case.get("expected_row")),
            "actual_rows": len(enriched),
            "transport_warnings": len(
                [warning for warning in connector_result.warnings if "failed for" in warning]
            ),
        },
    ]
    invalid_detected = sum(
        1 for evidence_id in invalid_ids if detected_by_id.get(evidence_id) is False
    ) + (len(transport_cases) if transport_detected else 0)
    scorecard = {
        "schema_version": "research_engine.eval.v1",
        "generated_at": utc_now(),
        "suite_id": "m0-evidence-validity",
        "offline": True,
        "fixture": _display_fixture_path(fixture_path),
        "summary": {
            "passed": all(check["passed"] for check in checks),
            "checks_passed": sum(1 for check in checks if check["passed"]),
            "checks_total": len(checks),
            "probes_total": len(cases),
            "invalid_probes_detected": invalid_detected,
            "invalid_probes_total": len(invalid_ids) + len(transport_cases),
        },
        "checks": checks,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "scorecard.json").write_text(
        json.dumps(scorecard, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return scorecard


def run_eval_v2(
    *,
    fixture_path: Path = DEFAULT_V2_FIXTURE,
    output_dir: Path,
) -> dict[str, Any]:
    """Run deterministic B1-B10 while embedding the unchanged M0 validity gate."""

    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    m0 = run_eval(output_dir=output_dir / "m0")
    checks: list[dict[str, Any]] = []

    b1 = fixture["b1"]
    stale = enrich_row_freshness(
        b1["row"],
        as_of=b1["as_of"],
        window_days=int(b1["window_days"]),
    )
    stale["freshness_window_days"] = int(b1["window_days"])
    stale_rows, _ = enrich_rows_with_quality(
        [stale], topic="current memory prices", pack={"id": "generic"}
    )
    checks.append(
        benchmark_check(
            "B1",
            stale_rows[0]["freshness_status"] == "stale"
            and stale_rows[0]["claim_eligible"] is False,
            {"freshness_status": stale_rows[0]["freshness_status"]},
        )
    )

    b2_topic = str(fixture["b2"]["topic"])
    b2_engine = ResearchEngine(
        output_dir=output_dir / "b2-runs",
        connectors={"github_public_search": _FixtureGitHubConnector},
    )
    b2_run = b2_engine.run(
        b2_topic,
        depth="deep",
        run_date="2026-07-16",
        search_provider="none",
    )
    b2_dir = Path(b2_run.run_dir)
    b2_plan = json.loads((b2_dir / "query_plan.json").read_text(encoding="utf-8"))
    b2_execution = json.loads(
        (b2_dir / "collection_execution.json").read_text(encoding="utf-8")
    )
    b2_rows = [
        json.loads(line)
        for line in (b2_dir / "evidence.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    b2_repositories = {
        str(row.get("title") or "")
        for row in b2_rows
        if row.get("connector") == "github_public_search"
    }
    b2_executed_facets = {
        str(record.get("facet_id") or "")
        for record in b2_execution.get("requests") or []
        if record.get("connector") == "github_public_search"
        and record.get("status") in {"ok", "warning", "cache_hit"}
    }
    checks.append(
        benchmark_check(
            "B2",
            {"project_vllm_repository", "project_sglang_repository"}.issubset(
                b2_executed_facets
            )
            and b2_repositories == {
                "vllm-project/vllm",
                "sgl-project/sglang",
            }
            and b2_plan["query_reconciliation"]["executed"] >= 2,
            {
                "run_id": b2_run.run_id,
                "executed_facets": sorted(b2_executed_facets),
                "repositories": sorted(b2_repositories),
            },
        )
    )

    b3 = build_claim_chains(fixture["b3"]["rows"], claim_id="contested", min_support=2)
    checks.append(
        benchmark_check(
            "B3",
            b3["stance"] == "conflicted"
            and b3["confidence_ceiling"] == "medium"
            and b3["support_chain"]["independent_source_count"] == 1
            and b3["opposition_chain"]["independent_source_count"] == 1,
            b3,
        )
    )

    b4_fixture = fixture["b4"]
    b4_engine = ResearchEngine(
        output_dir=output_dir / "b4-runs",
        connectors={
            "web_search": _FixtureDiscoveryConnector(
                b4_fixture["results"],
                empty_first_facets={"overview"},
            ),
            "web_page": _FixtureCanonicalConnector,
        },
    )
    b4_run = b4_engine.run(
        b4_fixture["topic"],
        depth="quick",
        run_date="2026-07-16",
        search_provider="anysearch",
    )
    b4_dir = Path(b4_run.run_dir)
    b4_rows = [
        json.loads(line)
        for line in (b4_dir / "evidence.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    b4_execution = json.loads(
        (b4_dir / "collection_execution.json").read_text(encoding="utf-8")
    )
    b4_repair = json.loads(
        (b4_dir / "repair_record.json").read_text(encoding="utf-8")
    )
    b4_canonical_urls = [
        str(row.get("url") or "")
        for row in b4_rows
        if row.get("connector") == "web_page" and row.get("content_valid") is True
    ]
    b4_pass_ids = {
        str(record.get("pass_id") or "")
        for record in b4_execution.get("requests") or []
    }
    checks.append(
        benchmark_check(
            "B4",
            any("jsoncanvas.org/spec" in url for url in b4_canonical_urls)
            and any("github.com/obsidianmd/jsoncanvas" in url for url in b4_canonical_urls)
            and "canonical-refetch" in b4_pass_ids
            and b4_repair["attempted"] is True
            and b4_repair["pass_id"] == "pass-2"
            and all(not pass_id.startswith("pass-3") for pass_id in b4_pass_ids),
            {
                "run_id": b4_run.run_id,
                "canonical_urls": b4_canonical_urls,
                "pass_ids": sorted(b4_pass_ids),
                "repair_stop_reason": b4_repair["stop_reason"],
            },
        )
    )

    b5 = fixture["b5"]
    ranked = rank_github_repositories(
        b5["repositories"],
        str(b5["query"]),
        as_of="2026-07-16",
    )
    canonical = {"openai/deep-research", "langchain-ai/open_deep_research"}
    top = [row for row in ranked[:12] if row["title"] in canonical]
    checks.append(
        benchmark_check(
            "B5",
            {row["title"] for row in top} == canonical
            and all(row.get("license_spdx") and row.get("pushed_at") for row in top),
            {"top": [row["title"] for row in ranked[:12]]},
        )
    )

    checks.append(
        benchmark_check(
            "B6",
            bool(m0["summary"]["passed"])
            and m0["summary"]["checks_passed"] == 9
            and m0["summary"]["invalid_probes_detected"] == 5,
            {"m0_summary": m0["summary"]},
        )
    )

    rerun_dir = output_dir / "b7-runs"
    rerun_dir.mkdir(parents=True, exist_ok=True)
    b7_args = [
        "run",
        "immutable eval rerun",
        "--dry-run",
        "--output",
        str(rerun_dir),
        "--search-provider",
        "none",
        "--as-of",
        "2026-07-16",
    ]
    with redirect_stdout(io.StringIO()):
        first_exit = cli_main(b7_args)
    first_entry = json.loads(
        (rerun_dir / "journal.jsonl").read_text(encoding="utf-8").splitlines()[-1]
    )
    first_manifest_path = rerun_dir / str(first_entry["run_id"]) / "run_manifest.json"
    first_manifest = first_manifest_path.read_bytes()
    with redirect_stdout(io.StringIO()):
        second_exit = cli_main(b7_args)
    journal = [
        json.loads(line)
        for line in (rerun_dir / "journal.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    first_entry, second_entry = journal[-2:]
    checks.append(
        benchmark_check(
            "B7",
            first_exit == second_exit == 0
            and first_entry["run_id"] != second_entry["run_id"]
            and first_manifest
            == first_manifest_path.read_bytes()
            and first_entry["exit_status"] == second_entry["exit_status"] == 0
            and first_entry["started_at"] <= first_entry["ended_at"]
            and second_entry["started_at"] <= second_entry["ended_at"],
            {
                "run_ids": [first_entry["run_id"], second_entry["run_id"]],
                "journal_entries": 2,
                "first_manifest_immutable": first_manifest == first_manifest_path.read_bytes(),
            },
        )
    )

    b8 = fixture["b8"]
    html = extract_content(
        b8["html"], content_type="text/html", parent_evidence_id="b8-html", chunk_chars=80
    )
    pdf = extract_content(
        b"%PDF fixture",
        content_type="application/pdf",
        parent_evidence_id="b8-pdf",
        pdf_extractor=lambda _body: str(b8["pdf_text"]),
    )
    chunks = [*html["chunks"], *pdf["chunks"]]
    checks.append(
        benchmark_check(
            "B8",
            html["tables"] == [[
                ["Vendor", "Product"],
                ["Micron", "HBM3E"],
            ]]
            and pdf["content_valid"]
            and len({chunk["chunk_id"] for chunk in chunks}) == len(chunks)
            and all(chunk["parent_evidence_id"] for chunk in chunks),
            {"table_count": len(html["tables"]), "chunk_count": len(chunks)},
        )
    )

    b9 = fixture["b9"]
    b9_engine = ResearchEngine(
        output_dir=output_dir / "b9-runs",
        connectors={
            "web_search": _FixtureDiscoveryConnector(),
            "web_page": _FixtureCanonicalConnector,
        },
    )
    b9_run = b9_engine.run(
        b9["topic"],
        pack_id="market_landscape",
        depth="audit",
        run_date="2026-07-16",
        research_scope=b9["scope"],
        search_provider="anysearch",
    )
    b9_dir = Path(b9_run.run_dir)
    market_plan = json.loads((b9_dir / "query_plan.json").read_text(encoding="utf-8"))
    market_coverage = json.loads(
        (b9_dir / "facet_coverage.json").read_text(encoding="utf-8")
    )
    market_claims = json.loads(
        (b9_dir / "claim_review.json").read_text(encoding="utf-8")
    )
    market_execution = json.loads(
        (b9_dir / "collection_execution.json").read_text(encoding="utf-8")
    )
    checks.append(
        benchmark_check(
            "B9",
            not market_coverage["missing_required_facets"]
            and market_coverage["required_facets"] == 7
            and market_coverage["required_facets_covered"] == 7
            and market_plan["claim_context"] == {
                "as_of": "2026-07-16",
                "definition": ["hosted AI inference platforms"],
                "geography": ["US"],
            }
            and market_claims["claim_context"] == {
                "as_of": "2026-07-16",
                "definition": ["hosted AI inference platforms"],
                "geography": ["US"],
            }
            and market_execution["request_count"] >= 8,
            {
                "run_id": b9_run.run_id,
                "coverage": market_coverage,
                "claim_context": market_claims["claim_context"],
                "request_count": market_execution["request_count"],
            },
        )
    )

    b10 = fixture["b10"]
    snapshot = build_job_market_snapshot(
        b10["rows"],
        scope=b10["scope"],
        requested_sources=["Anthropic", "OpenAI"],
        checked_sources=["Anthropic", "OpenAI"],
    )
    counts = snapshot["counts"]
    checks.append(
        benchmark_check(
            "B10",
            counts["active"] == 1
            and counts["duplicate"] == 1
            and counts["closed"] == 1
            and sum(value for key, value in counts.items() if key != "observed")
            == counts["observed"]
            and snapshot["coverage"]["denominator"] == 2
            and snapshot["trend"] is None,
            {"counts": counts, "coverage": snapshot["coverage"]},
        )
    )

    scorecard = {
        "schema_version": "research_engine.eval.v2",
        "generated_at": utc_now(),
        "suite_id": "m2-general-research-b1-b10",
        "offline": True,
        "fixture": _display_fixture_path(fixture_path),
        "summary": {
            "passed": all(check["passed"] for check in checks),
            "checks_passed": sum(1 for check in checks if check["passed"]),
            "checks_total": len(checks),
            "invalid_probes_detected": m0["summary"]["invalid_probes_detected"],
            "invalid_probes_total": m0["summary"]["invalid_probes_total"],
            "m0_checks_passed": m0["summary"]["checks_passed"],
            "m0_checks_total": m0["summary"]["checks_total"],
        },
        "benchmarks": checks,
        "m0_scorecard": m0,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "scorecard.json").write_text(
        json.dumps(scorecard, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return scorecard


def benchmark_check(benchmark_id: str, passed: bool, detail: Any) -> dict[str, Any]:
    return {"id": benchmark_id, "passed": bool(passed), "detail": detail}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run offline Research Engine regression evals.")
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--suite", choices=["v1", "v2"], default="v2")
    parser.add_argument("--output", type=Path, default=Path("eval-results"))
    args = parser.parse_args(argv)
    if args.fixture or args.suite == "v1":
        scorecard = run_eval(
            fixture_path=args.fixture or DEFAULT_FIXTURE,
            output_dir=args.output,
        )
    else:
        scorecard = run_eval_v2(output_dir=args.output)
    print(args.output / "scorecard.json")
    return 0 if scorecard["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
