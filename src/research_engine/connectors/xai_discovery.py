"""xAI Web/X Search discovery connector; citations are never claim evidence."""

from __future__ import annotations

import json
import os
from typing import Any, Callable
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from research_engine.models import CollectionRequest, CollectionResult, utc_now
from research_engine.targets import ResearchTarget


XAI_API_URL = "https://api.x.ai/v1/responses"
DEFAULT_MODEL = "grok-4.5"
Transport = Callable[..., dict[str, Any]]


class XaiDiscoveryConnector:
    connector_id = "xai_discovery"

    def __init__(self, *, transport: Transport | None = None) -> None:
        self.transport = transport

    def collect(self, request: CollectionRequest) -> CollectionResult:
        target = ResearchTarget.from_mapping(dict(request.source.get("target") or {}))
        api_key = str(
            os.environ.get("GROK_API_KEY") or os.environ.get("XAI_API_KEY") or ""
        ).strip()
        if self.transport is None and not api_key:
            return CollectionResult(
                source_id=request.source_id,
                connector=self.connector_id,
                rows=[],
                warnings=["xAI discovery unavailable: GROK_API_KEY or XAI_API_KEY is not set"],
                metadata={"status": "unavailable", "authority": "discovery_only"},
            )

        payload = build_payload(target, run_date=request.run_date)
        try:
            response = (self.transport or post_xai_response)(
                payload=payload,
                api_key=api_key,
                timeout=float(request.source.get("timeout_seconds") or 45.0),
            )
            citations = extract_citation_urls(response)[: request.max_results]
        except Exception as exc:
            error_type = type(exc).__name__
            return CollectionResult(
                source_id=request.source_id,
                connector=self.connector_id,
                rows=[],
                warnings=[f"xAI discovery failed: {error_type}"],
                metadata={
                    "status": "failed",
                    "authority": "discovery_only",
                    "error_type": error_type,
                },
            )
        rows = [
            citation_row(url, source_id=request.source_id, index=index)
            for index, url in enumerate(citations, start=1)
        ]
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=rows,
            warnings=[] if rows else ["xAI discovery returned no cited public URLs"],
            metadata={
                "status": "ready" if rows else "empty",
                "authority": "discovery_only",
                "citation_count": len(rows),
                "model": str(payload.get("model") or ""),
            },
        )


def build_payload(target: ResearchTarget, *, run_date: str) -> dict[str, Any]:
    prompt = (
        "Discover public URLs only for this software-engineering hiring target. "
        "First find current final official job-description URLs, then official company interview-process "
        "pages, then recent public candidate or developer-community reports. Do not use login-only content, "
        "do not bypass access controls, and do not treat search pages, careers landing pages, generic prep "
        "repositories, or your own summary as facts. Return concise cited findings; the caller will ignore "
        "your prose and independently fetch and verify every citation.\n"
        f"As of: {run_date}. Target: {json.dumps(target.as_dict(), ensure_ascii=False, sort_keys=True)}"
    )
    return {
        "model": str(os.environ.get("XAI_MODEL") or os.environ.get("GROK_MODEL") or DEFAULT_MODEL),
        "input": [{"role": "user", "content": prompt}],
        "tools": [{"type": "web_search"}, {"type": "x_search"}],
    }


def post_xai_response(*, payload: dict[str, Any], api_key: str, timeout: float) -> dict[str, Any]:
    request = Request(
        XAI_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "research-engine/0.2",
        },
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not isinstance(result, dict):
        raise ValueError("xAI Responses API returned a non-object payload")
    return result


def extract_citation_urls(response: dict[str, Any]) -> list[str]:
    if not isinstance(response, dict):
        raise ValueError("xAI Responses API returned a non-object payload")
    seen: set[str] = set()
    urls: list[str] = []

    def add(value: Any) -> None:
        url = str(value or "").strip()
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or url in seen:
            return
        seen.add(url)
        urls.append(url)

    for value in response.get("citations") or []:
        add(value)
    for item in response.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            for annotation in content.get("annotations") or []:
                if not isinstance(annotation, dict) or annotation.get("type") != "url_citation":
                    continue
                nested = annotation.get("url_citation")
                add(annotation.get("url"))
                if isinstance(nested, dict):
                    add(nested.get("url"))
    return urls


def citation_row(url: str, *, source_id: str, index: int) -> dict[str, Any]:
    host = urlsplit(url).netloc.lower().removeprefix("www.")
    return {
        "source_id": source_id,
        "connector": XaiDiscoveryConnector.connector_id,
        "title": f"xAI cited candidate {index}: {host}",
        "url": url,
        "final_url": "",
        "publisher": host,
        "captured_at": utc_now(),
        "text": "",
        "source_kind": "discovery_candidate",
        "source_class": "discovery_only",
        "access_mode": "xai_public_search_citation",
        "discovered_via": "xai_x_search" if host in {"x.com", "twitter.com"} else "xai_web_search",
        "is_final_page": False,
        "current_status": "unknown",
        "source_confidence": "medium",
    }
