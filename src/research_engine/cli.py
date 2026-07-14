"""Command-line interface for Research Engine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from research_engine.doctor import render_doctor_text, run_doctor
from research_engine.runner import ResearchEngine
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
    )
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
    )
    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
