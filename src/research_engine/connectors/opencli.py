"""Optional OpenCLI bridge connector."""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
from typing import Any, Callable

from research_engine.models import CollectionRequest, CollectionResult, utc_now
from research_engine.security import (
    allowed_executable,
    command_risk_terms,
    redact_command,
    redact_text,
    sanitize_for_artifact,
)


TITLE_KEYS = ("title", "headline", "name", "fullName", "full_name")
URL_KEYS = ("url", "html_url", "link", "permalink", "tweet_url", "webpage_url")
TEXT_KEYS = ("text", "text_excerpt", "content", "body", "description", "summary", "snippet")
AUTHOR_KEYS = ("author", "user", "username", "screen_name", "channel", "owner")
PUBLISHED_KEYS = ("published_at", "created_at", "updated_at", "updatedAt", "timestamp", "date")


class OpenCliBridgeConnector:
    connector_id = "opencli_bridge"

    def __init__(
        self,
        *,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        which: Callable[[str], str | None] = shutil.which,
        allowed_executables: tuple[str, ...] = ("opencli",),
    ) -> None:
        self.runner = runner
        self.which = which
        self.allowed_executables = allowed_executables

    def collect(self, request: CollectionRequest) -> CollectionResult:
        max_results = int(request.max_results or request.source.get("max_results") or 5)
        platform = str(request.source.get("platform") or "opencli")
        query = str(request.source.get("query") or request.topic)
        command_templates = command_templates_from_source(request.source)
        rows: list[dict[str, Any]] = []
        warnings: list[str] = []
        rendered_commands: list[list[str]] = []

        if not command_templates:
            warnings.append(
                "opencli_bridge requires a command or command_templates source field; "
                "no OpenCLI command was run"
            )
            return self.result(
                request,
                rows=rows,
                warnings=warnings,
                platform=platform,
                rendered_commands=rendered_commands,
            )

        for template in command_templates:
            try:
                command = render_command_template(
                    template,
                    platform=platform,
                    query=query,
                    max_results=max_results,
                )
            except Exception as exc:
                warnings.append(f"opencli_bridge could not render command template: {redact_text(exc)}")
                continue
            rendered_commands.append(command)
            executable = command[0] if command else ""
            allowed = allowed_executable(command, self.allowed_executables)
            if executable and allowed is None:
                warnings.append(
                    "opencli_bridge rejected executable outside allowlist: "
                    f"{redact_text(executable)}"
                )
                continue
            risk_terms = command_risk_terms(command, ignored_values=[query])
            if risk_terms:
                warnings.append(
                    "opencli_bridge rejected command with unsafe term(s): "
                    + ",".join(risk_terms)
                )
                continue
            if not executable:
                warnings.append("opencli_bridge rendered an empty command")
                continue
            if self.which(executable) is None:
                warnings.append(f"opencli_bridge command not found on PATH: {executable}")
                continue
            try:
                completed = self.runner(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=float(request.source.get("timeout_seconds") or 60),
                    check=False,
                )
            except Exception as exc:
                warnings.append(f"opencli_bridge {executable} failed to start: {redact_text(exc)}")
                continue
            if completed.returncode != 0:
                warnings.append(
                    f"opencli_bridge {executable} exited {completed.returncode}: "
                    f"{redact_text((completed.stderr or '').strip())[:300]}"
                )
                continue
            rows.extend(
                normalize_output(
                    completed.stdout or "",
                    request=request,
                    platform=platform,
                    query=query,
                    command=command,
                    limit=max_results - len(rows),
                )
            )
            if len(rows) >= max_results:
                rows = rows[:max_results]
                break
        return self.result(
            request,
            rows=rows,
            warnings=warnings,
            platform=platform,
            rendered_commands=rendered_commands,
        )

    def result(
        self,
        request: CollectionRequest,
        *,
        rows: list[dict[str, Any]],
        warnings: list[str],
        platform: str,
        rendered_commands: list[list[str]],
    ) -> CollectionResult:
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=rows,
            warnings=warnings,
            metadata={
                "platform": platform,
                "opencli_installed": self.which("opencli") is not None,
                "command_count": len(rendered_commands),
                "commands": [redact_command(command) for command in rendered_commands],
            },
        )


def command_templates_from_source(source: dict[str, Any]) -> list[str | list[str]]:
    templates: list[str | list[str]] = []
    command = source.get("command")
    if isinstance(command, str) and command.strip():
        templates.append(command)
    elif isinstance(command, list) and command:
        templates.append([str(part) for part in command])
    raw_templates = source.get("command_templates") or []
    if isinstance(raw_templates, str):
        raw_templates = [raw_templates]
    elif not isinstance(raw_templates, list):
        raw_templates = []
    for item in raw_templates:
        if isinstance(item, str) and item.strip():
            templates.append(item)
        elif isinstance(item, list) and item:
            templates.append([str(part) for part in item])
    return templates


def render_command_template(
    template: str | list[str],
    *,
    platform: str,
    query: str,
    max_results: int,
) -> list[str]:
    parts = shlex.split(template) if isinstance(template, str) else list(template)
    return [
        part.format(platform=platform, query=query, max_results=max_results)
        for part in parts
    ]


def normalize_output(
    stdout: str,
    *,
    request: CollectionRequest,
    platform: str,
    query: str,
    command: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    payloads = parse_structured_output(stdout)
    if payloads:
        rows: list[dict[str, Any]] = []
        for payload in payloads[:limit]:
            row = row_from_payload(
                payload,
                request=request,
                platform=platform,
                query=query,
                command=command,
            )
            if row:
                rows.append(row)
        return rows
    text = " ".join(redact_text(stdout).split())
    if not text:
        return []
    return [
        {
            "source_id": request.source_id,
            "connector": OpenCliBridgeConnector.connector_id,
            "platform": platform,
            "title": f"OpenCLI {platform} output",
            "url": "",
            "text": text[:2000],
            "text_excerpt": text[:2000],
            "captured_at": utc_now(),
            "query": redact_text(query),
            "source_kind": str(request.source.get("source_kind") or "opencli_cli_output"),
            "source_confidence": str(request.source.get("source_confidence") or "medium"),
            "access_mode": str(request.source.get("access_mode") or "opencli_upstream_cli"),
            "metrics": {"command": redact_command(command)},
        }
    ]


def parse_structured_output(stdout: str) -> list[dict[str, Any]]:
    text = stdout.strip()
    if not text:
        return []
    try:
        return extract_items(json.loads(text))
    except json.JSONDecodeError:
        pass
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        clean = line.strip()
        if not clean:
            continue
        try:
            rows.extend(extract_items(json.loads(clean)))
        except json.JSONDecodeError:
            continue
    return rows


def extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("items", "results", "data", "posts", "tweets", "videos", "articles", "links"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    return []


def row_from_payload(
    payload: dict[str, Any],
    *,
    request: CollectionRequest,
    platform: str,
    query: str,
    command: list[str],
) -> dict[str, Any] | None:
    safe_payload = sanitize_for_artifact(payload)
    if not isinstance(safe_payload, dict):
        safe_payload = {}
    url = first_string(safe_payload, URL_KEYS)
    text = first_string(safe_payload, TEXT_KEYS)
    title = first_string(safe_payload, TITLE_KEYS) or text[:90] or url
    if not title and not text and not url:
        return None
    fallback_text = json.dumps(safe_payload, ensure_ascii=False)[:2000]
    payload_metrics = sanitize_for_artifact(safe_payload.get("metrics") or {})
    if not isinstance(payload_metrics, dict):
        payload_metrics = {}
    return {
        "source_id": request.source_id,
        "connector": OpenCliBridgeConnector.connector_id,
        "platform": str(safe_payload.get("platform") or platform),
        "title": title,
        "url": url,
        "author": first_string(safe_payload, AUTHOR_KEYS),
        "published_at": first_string(safe_payload, PUBLISHED_KEYS),
        "captured_at": str(safe_payload.get("captured_at") or utc_now()),
        "query": redact_text(str(safe_payload.get("query") or query)),
        "text": text or fallback_text,
        "text_excerpt": text[:2000] if text else fallback_text,
        "source_kind": str(safe_payload.get("source_kind") or request.source.get("source_kind") or "opencli_result"),
        "source_confidence": str(
            safe_payload.get("source_confidence") or request.source.get("source_confidence") or "medium"
        ),
        "access_mode": str(safe_payload.get("access_mode") or request.source.get("access_mode") or "opencli_upstream_cli"),
        "metrics": {**payload_metrics, "command": redact_command(command)},
    }


def first_string(payload: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            nested = first_string(value, ("login", "name", "url", "html_url"))
            if nested:
                return nested
    return ""
