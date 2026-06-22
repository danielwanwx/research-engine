"""Optional AgentReach/upstream CLI bridge connector."""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
from typing import Any, Callable

from research_engine.models import CollectionRequest, CollectionResult, utc_now


DEFAULT_PLATFORM_COMMAND_TEMPLATES: dict[str, tuple[str, ...]] = {
    "x": ('twitter search "{query}" -n {max_results}',),
    "reddit": ('rdt search "{query}" -n {max_results}',),
    "github": (
        'gh search repos "{query}" --limit {max_results} '
        "--json fullName,url,description,stargazersCount,updatedAt"
    ),
    "youtube": ('yt-dlp "ytsearch{max_results}:{query}" --dump-json --no-playlist',),
}

TITLE_KEYS = ("title", "fullName", "full_name", "name", "headline")
URL_KEYS = ("url", "html_url", "link", "permalink", "tweet_url", "webpage_url")
TEXT_KEYS = ("text", "text_excerpt", "content", "body", "description", "summary", "snippet")
AUTHOR_KEYS = ("author", "user", "username", "screen_name", "channel", "owner")
PUBLISHED_KEYS = ("published_at", "created_at", "updatedAt", "updated_at", "timestamp", "date")


class AgentReachBridgeConnector:
    connector_id = "agent_reach_bridge"

    def __init__(
        self,
        *,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        which: Callable[[str], str | None] = shutil.which,
    ) -> None:
        self.runner = runner
        self.which = which

    def collect(self, request: CollectionRequest) -> CollectionResult:
        strategy = request.source.get("query_strategy") or {}
        max_results = int(request.max_results or strategy.get("max_results") or 5)
        platforms = [str(platform) for platform in strategy.get("platforms") or []]
        if not platforms:
            platforms = ["x", "reddit", "github", "youtube"]
        platform_queries = {
            str(key): str(value)
            for key, value in (strategy.get("platform_queries") or {}).items()
            if value
        }
        commands = build_command_specs(
            platforms=platforms,
            query=str(strategy.get("query") or request.topic),
            platform_queries=platform_queries,
            templates=[str(template) for template in strategy.get("command_templates") or []],
            max_results=max_results,
        )
        rows: list[dict[str, Any]] = []
        warnings: list[str] = []
        skipped: list[str] = []
        for spec in commands:
            command = spec["command"]
            executable = command[0] if command else ""
            if not executable or self.which(executable) is None:
                skipped.append(executable or "<empty>")
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
                warnings.append(f"agent_reach_bridge {executable} failed to start: {exc}")
                continue
            if completed.returncode != 0:
                warnings.append(
                    f"agent_reach_bridge {executable} exited {completed.returncode}: "
                    f"{(completed.stderr or '').strip()[:300]}"
                )
                continue
            rows.extend(
                normalize_output(
                    completed.stdout or "",
                    request=request,
                    platform=str(spec["platform"]),
                    query=str(spec["query"]),
                    command=command,
                    limit=max_results - len(rows),
                )
            )
            if len(rows) >= max_results:
                rows = rows[:max_results]
                break
        if skipped and not rows:
            warnings.append(
                "agent_reach_bridge found no runnable upstream commands; install AgentReach/tools "
                "or pass --agent-reach-command. missing="
                + ",".join(sorted(set(skipped)))
            )
        elif skipped:
            warnings.append(
                "agent_reach_bridge skipped missing upstream commands: "
                + ",".join(sorted(set(skipped)))
            )
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=rows,
            warnings=warnings,
            metadata={
                "platforms": platforms,
                "agent_reach_installed": self.which("agent-reach") is not None,
                "command_count": len(commands),
            },
        )


def build_command_specs(
    *,
    platforms: list[str],
    query: str,
    platform_queries: dict[str, str],
    templates: list[str],
    max_results: int,
) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    if templates:
        for template in templates:
            for platform in platforms:
                platform_query = platform_queries.get(platform) or query
                specs.append(
                    {
                        "platform": platform,
                        "query": platform_query,
                        "command": render_command_template(
                            template,
                            platform=platform,
                            query=platform_query,
                            max_results=max_results,
                        ),
                    }
                )
        return specs
    for platform in platforms:
        for template in DEFAULT_PLATFORM_COMMAND_TEMPLATES.get(platform, ()):
            platform_query = platform_queries.get(platform) or query
            specs.append(
                {
                    "platform": platform,
                    "query": platform_query,
                    "command": render_command_template(
                        template,
                        platform=platform,
                        query=platform_query,
                        max_results=max_results,
                    ),
                }
            )
    return specs


def render_command_template(
    template: str,
    *,
    platform: str,
    query: str,
    max_results: int,
) -> list[str]:
    return [
        part.format(platform=platform, query=query, max_results=max_results)
        for part in shlex.split(template)
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
    payloads = parse_structured_output(stdout)
    if payloads:
        rows: list[dict[str, Any]] = []
        for payload in payloads[: max(0, limit)]:
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
    text = " ".join(stdout.split())
    if not text or limit <= 0:
        return []
    return [
        {
            "source_id": request.source_id,
            "connector": AgentReachBridgeConnector.connector_id,
            "platform": platform,
            "title": f"AgentReach {platform} output",
            "url": "",
            "text": text[:2000],
            "text_excerpt": text[:2000],
            "captured_at": utc_now(),
            "query": query,
            "source_kind": "agent_reach_cli_output",
            "source_confidence": "medium",
            "access_mode": "agent_reach_upstream_cli",
            "metrics": {"command": command},
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
        try:
            rows.extend(extract_items(json.loads(line.strip())))
        except json.JSONDecodeError:
            continue
    return rows


def extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("items", "results", "data", "repos", "tweets", "posts", "videos"):
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
    url = first_string(payload, URL_KEYS)
    text = first_string(payload, TEXT_KEYS)
    title = first_string(payload, TITLE_KEYS) or text[:90] or url
    if not title and not text and not url:
        return None
    return {
        "source_id": request.source_id,
        "connector": AgentReachBridgeConnector.connector_id,
        "platform": str(payload.get("platform") or platform),
        "title": title,
        "url": url,
        "author": first_string(payload, AUTHOR_KEYS),
        "published_at": first_string(payload, PUBLISHED_KEYS),
        "captured_at": str(payload.get("captured_at") or utc_now()),
        "query": str(payload.get("query") or query),
        "text": text or json.dumps(payload, ensure_ascii=False)[:2000],
        "text_excerpt": text[:2000] if text else json.dumps(payload, ensure_ascii=False)[:2000],
        "source_kind": str(payload.get("source_kind") or "agent_reach_result"),
        "source_confidence": str(payload.get("source_confidence") or "medium"),
        "access_mode": str(payload.get("access_mode") or "agent_reach_upstream_cli"),
        "metrics": {"command": command},
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
