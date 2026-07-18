"""Environment and optional connector capability checks."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import importlib.util
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from typing import Any, Callable

from research_engine.connectors.authenticated_browser import (
    LOGIN_BROWSER_ENV,
    resolve_login_browser,
)
from research_engine.models import utc_now
from research_engine.state import CONNECTOR_CAPABILITIES_FILE, resolve_state_path, write_state_json


Runner = Callable[..., subprocess.CompletedProcess[str]]
Which = Callable[[str], str | None]


@dataclass(frozen=True)
class CapabilityCheck:
    id: str
    label: str
    available: bool
    version: str = ""
    path: str = ""
    warning: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


COMMAND_CHECKS: dict[str, dict[str, Any]] = {
    "agent-reach": {
        "label": "AgentReach installer/status CLI",
        "group": "agentreach",
        "version_args": ("--version",),
        "connector_ids": ("agent_reach_bridge",),
    },
    "twitter": {
        "label": "AgentReach Twitter/X CLI",
        "group": "agentreach",
        "version_args": ("--version",),
        "connector_ids": ("agent_reach_bridge",),
    },
    "rdt": {
        "label": "AgentReach Reddit CLI",
        "group": "agentreach",
        "version_args": ("--version",),
        "connector_ids": ("agent_reach_bridge",),
    },
    "xhs": {
        "label": "AgentReach Xiaohongshu CLI",
        "group": "agentreach",
        "version_args": ("--version",),
        "connector_ids": ("agent_reach_bridge",),
    },
    "xq": {
        "label": "AgentReach Xueqiu CLI",
        "group": "agentreach",
        "version_args": ("--version",),
        "connector_ids": ("agent_reach_bridge",),
    },
    "yt-dlp": {
        "label": "YouTube downloader/search CLI",
        "group": "agentreach",
        "version_args": ("--version",),
        "connector_ids": ("agent_reach_bridge",),
    },
    "gh": {
        "label": "GitHub CLI",
        "group": "agentreach",
        "version_args": ("--version",),
        "connector_ids": ("agent_reach_bridge",),
    },
    "opencli": {
        "label": "OpenCLI browser workflow CLI",
        "group": "opencli",
        "version_args": ("--version",),
        "connector_ids": ("opencli_bridge",),
    },
}

TARGETS = {"all", "agentreach", "opencli", "browser", "chrome"}


def run_doctor(
    *,
    target: str = "all",
    state_dir: Path | None = None,
    runner: Runner = subprocess.run,
    which: Which = shutil.which,
    write: bool = True,
) -> dict[str, Any]:
    resolved_target = target if target in TARGETS else "all"
    checks: list[CapabilityCheck] = [
        check_python_version(),
        check_import("research_engine", label="Research Engine package", required=True),
    ]
    checks.extend(command_checks_for_target(resolved_target, runner=runner, which=which))
    if resolved_target in {"all", "browser", "chrome"}:
        checks.append(check_import("playwright", label="Playwright browser renderer", required=False))
        checks.append(check_playwright_chromium())
        checks.append(check_login_browser())
        checks.append(check_gui_readiness())

    check_dicts = [check.as_dict() for check in checks]
    required_failures = [
        check
        for check in check_dicts
        if check.get("metadata", {}).get("required") and not check.get("available")
    ]
    optional_missing = [
        check
        for check in check_dicts
        if not check.get("metadata", {}).get("required") and not check.get("available")
    ]
    status = "failed" if required_failures else "complete_with_warnings" if optional_missing else "ok"
    report = {
        "generated_at": utc_now(),
        "target": resolved_target,
        "status": status,
        "python": {
            "version": platform.python_version(),
            "executable": sys.executable,
            "implementation": platform.python_implementation(),
        },
        "summary": {
            "check_count": len(check_dicts),
            "available_count": sum(1 for check in check_dicts if check.get("available")),
            "required_failure_count": len(required_failures),
            "optional_missing_count": len(optional_missing),
        },
        "checks": check_dicts,
    }
    if write:
        path = resolve_state_path(state_dir, CONNECTOR_CAPABILITIES_FILE)
        report["artifact_path"] = str(path)
        write_state_json(state_dir, CONNECTOR_CAPABILITIES_FILE, report)
    return report


def command_checks_for_target(
    target: str,
    *,
    runner: Runner,
    which: Which,
) -> list[CapabilityCheck]:
    checks = []
    for command, config in COMMAND_CHECKS.items():
        if target != "all" and config["group"] != target:
            continue
        checks.append(
            check_command(
                command,
                label=str(config["label"]),
                group=str(config["group"]),
                connector_ids=tuple(config.get("connector_ids") or ()),
                version_args=tuple(config.get("version_args") or ()),
                runner=runner,
                which=which,
            )
        )
    return checks


def check_python_version() -> CapabilityCheck:
    available = sys.version_info >= (3, 10)
    return CapabilityCheck(
        id="python",
        label="Python >=3.10",
        available=available,
        version=platform.python_version(),
        path=sys.executable,
        warning="" if available else "Research Engine requires Python 3.10 or newer.",
        metadata={"required": True, "group": "core"},
    )


def check_import(module: str, *, label: str, required: bool) -> CapabilityCheck:
    spec = importlib.util.find_spec(module)
    available = spec is not None
    origin = str(spec.origin or "") if spec else ""
    return CapabilityCheck(
        id=f"python_import:{module}",
        label=label,
        available=available,
        path=origin,
        warning="" if available else f"Python module is not importable: {module}",
        metadata={"required": required, "group": "python"},
    )


def check_playwright_chromium() -> CapabilityCheck:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return CapabilityCheck(
            id="browser:chromium",
            label="Playwright Chromium",
            available=False,
            warning="Playwright is not installed; install research-engine[browser].",
            metadata={"required": False, "group": "browser"},
        )
    try:
        playwright = sync_playwright().start()
        try:
            executable = Path(playwright.chromium.executable_path)
        finally:
            playwright.stop()
    except Exception as exc:
        return CapabilityCheck(
            id="browser:chromium",
            label="Playwright Chromium",
            available=False,
            warning=f"Unable to inspect Chromium: {type(exc).__name__}",
            metadata={"required": False, "group": "browser"},
        )
    available = executable.is_file()
    return CapabilityCheck(
        id="browser:chromium",
        label="Playwright Chromium",
        available=available,
        path=str(executable) if available else "",
        warning="" if available else "Run: playwright install chromium",
        metadata={"required": False, "group": "browser"},
    )


def check_login_browser(
    resolver: Callable[[], str] = resolve_login_browser,
) -> CapabilityCheck:
    path = resolver()
    available = bool(path)
    return CapabilityCheck(
        id="browser:login_chrome",
        label="Normal Chrome for user-controlled login",
        available=available,
        path=path,
        warning=(
            ""
            if available
            else f"Install Google Chrome or set {LOGIN_BROWSER_ENV} to its executable."
        ),
        metadata={"required": False, "group": "browser"},
    )


def check_gui_readiness() -> CapabilityCheck:
    gui_available = platform.system() in {"Darwin", "Windows"} or bool(
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    )
    return CapabilityCheck(
        id="browser:gui",
        label="Visible browser session",
        available=gui_available,
        warning="" if gui_available else "No desktop display is available for user-controlled login.",
        metadata={
            "required": False,
            "group": "browser",
            "interactive_stdin": sys.stdin.isatty(),
        },
    )


def check_command(
    command: str,
    *,
    label: str,
    group: str,
    connector_ids: tuple[str, ...],
    version_args: tuple[str, ...],
    runner: Runner,
    which: Which,
) -> CapabilityCheck:
    path = which(command)
    if not path:
        return CapabilityCheck(
            id=f"command:{command}",
            label=label,
            available=False,
            warning=f"Command not found on PATH: {command}",
            metadata={
                "required": False,
                "group": group,
                "command": command,
                "connector_ids": list(connector_ids),
            },
        )
    version = command_version(path, version_args=version_args, runner=runner)
    return CapabilityCheck(
        id=f"command:{command}",
        label=label,
        available=True,
        version=version,
        path=path,
        metadata={
            "required": False,
            "group": group,
            "command": command,
            "connector_ids": list(connector_ids),
        },
    )


def command_version(path: str, *, version_args: tuple[str, ...], runner: Runner) -> str:
    if not version_args:
        return ""
    try:
        completed = runner(
            [path, *version_args],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception as exc:
        return f"version check failed: {exc}"
    output = (completed.stdout or completed.stderr or "").strip().splitlines()
    return output[0][:200] if output else ""


def render_doctor_text(report: dict[str, Any]) -> str:
    lines = [
        "Research Engine doctor",
        f"Target: {report.get('target')}",
        f"Status: {report.get('status')}",
        f"Python: {(report.get('python') or {}).get('version')} ({(report.get('python') or {}).get('executable')})",
    ]
    artifact_path = report.get("artifact_path")
    if artifact_path:
        lines.append(f"Artifact: {artifact_path}")
    lines.append("")
    for check in report.get("checks") or []:
        marker = "ok" if check.get("available") else "missing"
        version = f" - {check.get('version')}" if check.get("version") else ""
        path = f" ({check.get('path')})" if check.get("path") else ""
        warning = f": {check.get('warning')}" if check.get("warning") else ""
        lines.append(f"- {marker}: {check.get('label')}{version}{path}{warning}")
    return "\n".join(lines) + "\n"
