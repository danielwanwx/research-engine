"""Interactive research wizard for non-CLI users."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Callable

from research_engine.models import ResearchRunResult
from research_engine.runner import ResearchEngine


InputFunc = Callable[[str], str]
OutputFunc = Callable[[str], None]


@dataclass(frozen=True)
class ResearchWizardPlan:
    topic: str
    depth: str
    platform_scope: str
    external_evidence_paths: list[Path]
    agent_reach: bool
    output_dir: Path = Path("runs")
    source_timeout_seconds: float = 10.0


def research_main(argv: list[str] | None = None) -> int:
    return run_research_wizard(argv)


def run_research_wizard(
    argv: list[str] | None = None,
    *,
    input_func: InputFunc = input,
    output_func: OutputFunc = print,
    engine_factory: Callable[..., ResearchEngine] = ResearchEngine,
) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"-h", "--help"}:
        output_func("Usage: research [research topic]")
        output_func("")
        output_func("Run an interactive read-only research wizard.")
        return 0

    try:
        plan = build_wizard_plan(args, input_func=input_func, output_func=output_func)
    except KeyboardInterrupt:
        output_func("")
        output_func("Canceled.")
        return 130
    if plan is None:
        output_func("Canceled.")
        return 130

    engine = engine_factory(
        output_dir=plan.output_dir,
        source_timeout_seconds=plan.source_timeout_seconds,
    )
    result = engine.run(
        plan.topic,
        depth=plan.depth,
        external_evidence_paths=plan.external_evidence_paths,
        platform_scope=plan.platform_scope,
        agent_reach=plan.agent_reach,
    )
    render_result(result, output_func=output_func)
    return 0


def build_wizard_plan(
    args: list[str],
    *,
    input_func: InputFunc,
    output_func: OutputFunc,
) -> ResearchWizardPlan | None:
    topic = " ".join(args).strip()
    output_func("Research Engine")
    output_func("Evidence-first, read-only research loop.")
    output_func("")
    if not topic:
        topic = ask_text("What do you want to research?", input_func=input_func).strip()
    if not topic:
        output_func("A research topic is required.")
        return None

    depth = ask_choice(
        "Research depth?",
        [
            ("quick", "Quick scan"),
            ("deep", "Deep research (recommended)"),
            ("audit", "Audit-grade, stricter evidence pass"),
        ],
        default_index=1,
        input_func=input_func,
        output_func=output_func,
    )
    source_mode = ask_choice(
        "Which sources can I use?",
        [
            ("public", "Public web only"),
            ("external", "Public web + JSONL evidence you exported"),
            ("bridges", "Public web + configured AgentReach/OpenCLI bridges"),
            ("all", "All configured read-only sources"),
        ],
        default_index=0,
        input_func=input_func,
        output_func=output_func,
    )
    platform_scope = "all" if source_mode in {"bridges", "all"} else "broad"
    agent_reach = source_mode in {"bridges", "all"}
    external_paths: list[Path] = []
    if source_mode in {"external", "all"}:
        output_func("")
        output_func("If you have logged-in, paid, or private evidence, export it to JSONL first.")
        output_func("Do not paste cookies, tokens, passwords, or API keys here.")
        raw_paths = ask_text(
            "JSONL file path(s), comma-separated; leave blank to skip:",
            input_func=input_func,
        )
        external_paths = parse_path_list(raw_paths)

    output_func("")
    output_func("Planned read-only run:")
    output_func(f"- topic: {topic}")
    output_func(f"- depth: {depth}")
    output_func(f"- platform scope: {platform_scope}")
    output_func(f"- external evidence files: {len(external_paths)}")
    output_func(f"- AgentReach bridge: {'enabled' if agent_reach else 'disabled'}")
    output_func("- safety: no posting, messaging, trading, uploads, or account mutation")
    confirmed = ask_yes_no("Run now?", input_func=input_func, default=False)
    if not confirmed:
        return None

    return ResearchWizardPlan(
        topic=topic,
        depth=depth,
        platform_scope=platform_scope,
        external_evidence_paths=external_paths,
        agent_reach=agent_reach,
    )


def ask_text(prompt: str, *, input_func: InputFunc) -> str:
    return input_func(f"{prompt} ").strip()


def ask_choice(
    prompt: str,
    choices: list[tuple[str, str]],
    *,
    default_index: int,
    input_func: InputFunc,
    output_func: OutputFunc,
) -> str:
    output_func(prompt)
    for index, (_, label) in enumerate(choices, start=1):
        suffix = " (default)" if index - 1 == default_index else ""
        output_func(f"[{index}] {label}{suffix}")
    while True:
        raw_value = input_func("> ").strip()
        if not raw_value:
            return choices[default_index][0]
        if raw_value.isdigit():
            index = int(raw_value)
            if 1 <= index <= len(choices):
                return choices[index - 1][0]
        output_func(f"Choose 1-{len(choices)}, or press Enter for the default.")


def ask_yes_no(prompt: str, *, input_func: InputFunc, default: bool) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    raw_value = input_func(f"{prompt} {suffix} ").strip().lower()
    if not raw_value:
        return default
    return raw_value in {"y", "yes"}


def parse_path_list(raw_paths: str) -> list[Path]:
    paths: list[Path] = []
    for value in raw_paths.split(","):
        text = value.strip()
        if text:
            paths.append(Path(text).expanduser())
    return paths


def render_result(result: ResearchRunResult, *, output_func: OutputFunc) -> None:
    output_func("")
    output_func("Research run finished.")
    output_func(f"- run status: {result.status}")
    output_func(f"- loop status: {result.loop_status or 'unknown'}")
    output_func(f"- stop reason: {result.stop_reason or 'unknown'}")
    output_func(f"- feedback actions: {result.feedback_action_count}")
    if result.warnings:
        output_func("- warnings:")
        for warning in result.warnings[:5]:
            output_func(f"  - {warning}")
    output_func("")
    output_func("Artifacts:")
    output_func(f"- {result.run_dir}/research_report.md")
    if result.pdf_report_path:
        output_func(f"- {result.pdf_report_path}")
    else:
        output_func(f"- PDF report: {result.pdf_report_status or 'failed'}")
    output_func(f"- {result.run_dir}/loop_record.json")
