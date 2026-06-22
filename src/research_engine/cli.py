"""Command-line interface for Research Engine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from research_engine.runner import ResearchEngine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run pack-driven research collection.")
    subparsers = parser.add_subparsers(dest="command")
    run_parser = subparsers.add_parser("run", help="Run a research collection.")
    add_run_arguments(run_parser)
    return parser


def add_run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("topic", help="Research topic or question.")
    parser.add_argument("--depth", choices=["quick", "deep", "audit"], default="quick")
    parser.add_argument("--pack", dest="pack_id", default="auto", help="Pack id, or 'auto'.")
    parser.add_argument("--pack-dir", type=Path, help="Directory containing JSON research packs.")
    parser.add_argument("--output", type=Path, default=Path("runs"), help="Output directory.")
    parser.add_argument("--dry-run", action="store_true", help="Write plan artifacts without collection.")
    parser.add_argument(
        "--external-evidence",
        action="append",
        type=Path,
        default=[],
        help="Import external evidence JSONL rows, e.g. exported logged-in browser captures.",
    )
    parser.add_argument("--max-workers", type=int, default=4, help="Maximum concurrent connector requests.")
    parser.add_argument("--retries", type=int, default=1, help="Retry count for failed connector requests.")
    parser.add_argument("--cache-dir", type=Path, help="Optional connector-result cache directory.")
    parser.add_argument(
        "--source-timeout-seconds",
        type=float,
        help="Optional soft timeout per connector request.",
    )


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if raw_args and raw_args[0] != "run" and not raw_args[0].startswith("-"):
        raw_args.insert(0, "run")
    args = build_parser().parse_args(raw_args)
    pack_id = None if args.pack_id in {None, "", "auto"} else args.pack_id
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
    )
    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
