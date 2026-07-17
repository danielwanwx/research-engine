"""Command-line interface for Research Engine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from research_engine.artifacts import append_jsonl
from research_engine.doctor import render_doctor_text, run_doctor
from research_engine.models import utc_now
from research_engine.runner import ResearchEngine
from research_engine.security import redact_command, redact_text
from research_engine.targets import ResearchTarget


COMMANDS = {"run", "doctor"}


def research_main(argv: list[str] | None = None) -> int:
    from research_engine.interactive import run_research_wizard

    return run_research_wizard(argv)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run evidence-first research collection.")
    subparsers = parser.add_subparsers(dest="command")
    run_parser = subparsers.add_parser("run", help="Run a research collection.")
    add_run_arguments(run_parser)
    doctor_parser = subparsers.add_parser(
        "doctor", help="Check local Research Engine capabilities."
    )
    add_doctor_arguments(doctor_parser)
    return parser


def add_run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("topic", help="Research topic or question.")
    parser.add_argument("--depth", choices=["quick", "deep", "audit"], default="quick")
    parser.add_argument("--pack", dest="pack_id", default="auto", help="Pack id, or 'auto'.")
    parser.add_argument("--pack-dir", type=Path, help="Directory containing JSON research packs.")
    parser.add_argument(
        "--scope-file",
        type=Path,
        help="JSON research_scope.v1 file for explicit profile and quantitative boundaries.",
    )
    parser.add_argument(
        "--search-provider",
        choices=["anysearch", "searxng", "none"],
        default="anysearch",
        help="Public web discovery provider; queries cross a third-party boundary unless 'none'.",
    )
    parser.add_argument(
        "--search-endpoint",
        default="",
        help="Explicit SearXNG endpoint; ignored by the anonymous AnySearch provider.",
    )
    parser.add_argument("--as-of", default="", help="Research snapshot date in YYYY-MM-DD form.")
    parser.add_argument("--output", type=Path, default=Path("runs"), help="Output directory.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Write plan artifacts without collection."
    )
    parser.add_argument(
        "--platform-scope",
        choices=["quick", "broad", "deep", "all"],
        default="broad",
        help="Platform coverage plan depth for web/forum/social discovery.",
    )
    parser.add_argument(
        "--external-evidence",
        action="append",
        type=Path,
        default=[],
        help="Import external evidence JSONL rows, e.g. exported logged-in browser captures.",
    )
    parser.add_argument(
        "--web-search-pages",
        action="store_true",
        help="Fetch public platform search result pages as bounded web_page seed evidence.",
    )
    parser.add_argument("--target-company", default="", help="Structured target company.")
    parser.add_argument(
        "--target-role-family", default="", help="Structured role family, e.g. software_engineering."
    )
    parser.add_argument("--target-role-title", default="", help="Structured target role title.")
    parser.add_argument("--target-level", default="", help="Structured target level.")
    parser.add_argument("--target-geography", default="", help="Structured target geography.")
    parser.add_argument("--target-team", default="", help="Optional structured target team.")
    parser.add_argument(
        "--agent-reach",
        action="store_true",
        help="Run optional AgentReach/upstream CLI bridge sources.",
    )
    parser.add_argument(
        "--agent-reach-command",
        action="append",
        default=[],
        help=(
            "Custom AgentReach/upstream CLI command template; placeholders: "
            "{query}, {platform}, {max_results}. Repeatable."
        ),
    )
    parser.add_argument(
        "--max-workers", type=int, default=4, help="Maximum concurrent connector requests."
    )
    parser.add_argument(
        "--retries", type=int, default=1, help="Retry count for failed connector requests."
    )
    parser.add_argument("--cache-dir", type=Path, help="Optional connector-result cache directory.")
    parser.add_argument(
        "--source-timeout-seconds",
        type=float,
        help="Optional soft timeout per connector request.",
    )
    parser.add_argument(
        "--overall-deadline-seconds",
        type=float,
        help="Optional overall connector deadline including retries and host delays.",
    )
    parser.add_argument(
        "--host-max-concurrency",
        type=int,
        default=2,
        help="Maximum concurrent requests per public host.",
    )
    parser.add_argument(
        "--host-delay-seconds",
        type=float,
        default=0.1,
        help="Minimum delay between starts for the same public host.",
    )


def add_doctor_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "target",
        nargs="?",
        choices=["all", "agentreach", "opencli", "chrome"],
        default="all",
        help="Capability group to check.",
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=Path("state"),
        help="Directory for capability artifacts.",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format for stdout.",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Do not write state/connector_capabilities.json.",
    )


def append_invocation_record(
    *,
    output_dir: Path,
    raw_args: list[str],
    started_at: str,
    exit_status: int,
    result: Any = None,
    error: BaseException | None = None,
) -> None:
    append_jsonl(
        output_dir / "journal.jsonl",
        {
            "schema_version": "invocation_journal.v1",
            "command": "run",
            "argv": redact_command(raw_args),
            "started_at": started_at,
            "ended_at": utc_now(),
            "exit_status": exit_status,
            "run_id": result.run_id if result is not None else None,
            "run_dir": result.run_dir if result is not None else None,
            "run_status": result.status if result is not None else None,
            "error_type": type(error).__name__ if error is not None else None,
            "error_message": redact_text(error) if error is not None else None,
        },
    )


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if raw_args and raw_args[0] not in COMMANDS and not raw_args[0].startswith("-"):
        raw_args.insert(0, "run")
    parser = build_parser()
    args = parser.parse_args(raw_args)
    if args.command == "doctor":
        report = run_doctor(target=args.target, state_dir=args.state_dir, write=not args.no_write)
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(render_doctor_text(report), end="")
        return 1 if report.get("status") == "failed" else 0
    started_at = utc_now()
    result = None
    rendered_result = ""
    try:
        pack_id = None if args.pack_id in {None, "", "auto"} else args.pack_id
        target_values = {
            "company": args.target_company,
            "role_family": args.target_role_family,
            "role_title": args.target_role_title,
            "level": args.target_level,
            "geography": args.target_geography,
            "team": args.target_team,
        }
        target = None
        if any(str(value or "").strip() for value in target_values.values()):
            try:
                target = ResearchTarget.from_mapping(target_values)
            except ValueError as exc:
                parser.error(str(exc))
        engine = ResearchEngine(
            pack_dir=args.pack_dir,
            output_dir=args.output,
            max_workers=args.max_workers,
            retries=args.retries,
            cache_dir=args.cache_dir,
            source_timeout_seconds=args.source_timeout_seconds,
            overall_deadline_seconds=args.overall_deadline_seconds,
            host_max_concurrency=args.host_max_concurrency,
            host_delay_seconds=args.host_delay_seconds,
        )
        research_scope = load_scope_file(args.scope_file) if args.scope_file else None
        result = engine.run(
            args.topic,
            depth=args.depth,
            dry_run=args.dry_run,
            pack_id=pack_id,
            external_evidence_paths=args.external_evidence,
            platform_scope=args.platform_scope,
            web_search_pages=args.web_search_pages,
            target=target,
            agent_reach=args.agent_reach,
            agent_reach_command_templates=args.agent_reach_command,
            research_scope=research_scope,
            search_provider=args.search_provider,
            search_endpoint=args.search_endpoint,
            as_of=args.as_of or None,
        )
        rendered_result = json.dumps(result.as_dict(), ensure_ascii=False, indent=2)
    except BaseException as exc:
        if isinstance(exc, KeyboardInterrupt):
            exit_status = 130
        elif isinstance(exc, SystemExit) and isinstance(exc.code, int):
            exit_status = exc.code
        else:
            exit_status = 1
        try:
            append_invocation_record(
                output_dir=args.output,
                raw_args=raw_args,
                started_at=started_at,
                exit_status=exit_status,
                result=result,
                error=exc,
            )
        except Exception as journal_error:
            print(f"invocation journal failed: {redact_text(journal_error)}", file=sys.stderr)
        raise
    append_invocation_record(
        output_dir=args.output,
        raw_args=raw_args,
        started_at=started_at,
        exit_status=0,
        result=result,
    )
    print(rendered_result)
    return 0


def load_scope_file(path: Path) -> dict[str, Any]:
    """Load an explicit scope object; semantic validation belongs to planning."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to load research scope: {type(exc).__name__}") from exc
    if not isinstance(payload, dict):
        raise ValueError("research scope must be a JSON object")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
