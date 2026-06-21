"""Command-line interface for Research Engine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_engine.runner import ResearchEngine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run pack-driven research collection.")
    parser.add_argument("topic", help="Research topic or question.")
    parser.add_argument("--depth", choices=["quick", "deep", "audit"], default="quick")
    parser.add_argument("--pack", dest="pack_id", help="Force a specific pack id.")
    parser.add_argument("--pack-dir", type=Path, help="Directory containing JSON research packs.")
    parser.add_argument("--output", type=Path, default=Path("runs"), help="Output directory.")
    parser.add_argument("--dry-run", action="store_true", help="Write plan artifacts without collection.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    engine = ResearchEngine(pack_dir=args.pack_dir, output_dir=args.output)
    result = engine.run(
        args.topic,
        depth=args.depth,
        dry_run=args.dry_run,
        pack_id=args.pack_id,
    )
    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
