"""AnySearch URL discovery; provider output is never claim evidence."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Callable
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from research_engine.call_policy import external_discovery_decision
from research_engine.models import CollectionRequest, CollectionResult, utc_now
from research_engine.targets import ResearchTarget


ANYSEARCH_API_URL = "https://api.anysearch.com/mcp"
CLIENT_HEADER = "research-engine/anysearch.v1"
Transport = Callable[..., dict[str, Any]]


class AnySearchConnector:
    connector_id = "anysearch_discovery"

    def __init__(self, *, transport: Transport | None = None) -> None:
        self.transport = transport

    def collect(self, request: CollectionRequest) -> CollectionResult:
        decision = external_discovery_decision(
            request.source,
            transport_injected=self.transport is not None,
        )
        if not decision["allowed"]:
            return CollectionResult(
                source_id=request.source_id,
                connector=self.connector_id,
                rows=[],
                warnings=[f"AnySearch discovery blocked: {decision['stop_reason']}"],
                metadata={
                    "status": "blocked",
                    "authority": "discovery_only",
                    **decision,
                    "external_calls_attempted": 0,
                },
            )
        target = ResearchTarget.from_mapping(dict(request.source.get("target") or {}))
        query_intent = str(request.source.get("query_intent") or "official_role")
        payload = build_payload(
            target,
            query_intent=query_intent,
            max_results=request.max_results,
        )
        api_key = str(os.environ.get("ANYSEARCH_API_KEY") or "").strip()
        try:
            response = (self.transport or post_anysearch_response)(
                payload=payload,
                api_key=api_key,
                timeout=float(request.source.get("timeout_seconds") or 20.0),
            )
            candidates = extract_candidates(response)[: request.max_results]
        except Exception as exc:
            error_type = type(exc).__name__
            return CollectionResult(
                source_id=request.source_id,
                connector=self.connector_id,
                rows=[],
                warnings=[f"AnySearch discovery failed: {error_type}"],
                metadata={
                    "status": "failed",
                    "authority": "discovery_only",
                    "error_type": error_type,
                    **decision,
                    "external_calls_attempted": int(self.transport is None),
                },
            )
        rows = [
            candidate_row(
                title=title,
                url=url,
                source_id=request.source_id,
                query_intent=query_intent,
                rank=rank,
                request_id=str(response.get("id") or ""),
            )
            for rank, (title, url) in enumerate(candidates, start=1)
        ]
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=rows,
            warnings=[] if rows else ["AnySearch discovery returned no public URLs"],
            metadata={
                "status": "ready" if rows else "empty",
                "authority": "discovery_only",
                "candidate_count": len(rows),
                **decision,
                "external_calls_attempted": int(self.transport is None),
            },
        )


def build_payload(
    target: ResearchTarget,
    *,
    query_intent: str,
    max_results: int,
) -> dict[str, Any]:
    intent = {
        "official_role": "current final official job description",
        "official_process": "official engineering interview process",
        "public_discussion": "recent public engineering candidate discussion",
    }.get(query_intent, "current public hiring information")
    target_text = " ".join(
        part
        for part in (
            target.company,
            target.role_title,
            target.level,
            target.geography,
            target.team,
        )
        if part
    )
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "search",
            "arguments": {
                "query": f"{target_text} {intent}",
                "max_results": max(1, min(int(max_results), 10)),
            },
        },
    }


def post_anysearch_response(
    *,
    payload: dict[str, Any],
    api_key: str,
    timeout: float,
) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "X-Anysearch-Client": CLIENT_HEADER,
        "User-Agent": "research-engine/0.2",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = Request(
        ANYSEARCH_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not isinstance(result, dict):
        raise ValueError("AnySearch returned a non-object response")
    if result.get("error"):
        raise ValueError("AnySearch returned a JSON-RPC error")
    return result


def extract_candidates(response: dict[str, Any]) -> list[tuple[str, str]]:
    seen: set[str] = set()
    candidates: list[tuple[str, str]] = []
    for item in (response.get("result") or {}).get("content") or []:
        if not isinstance(item, dict) or item.get("type") != "text":
            continue
        text = str(item.get("text") or "")
        for title, url in re.findall(r"\[([^\]]+)\]\((https?://[^\s)]+)\)", text):
            _add_candidate(candidates, seen, title=title, url=url)
        for url in re.findall(r"https?://[^\s<>\])]+", text):
            _add_candidate(candidates, seen, title=urlsplit(url).netloc, url=url)
    return candidates


def _add_candidate(
    candidates: list[tuple[str, str]],
    seen: set[str],
    *,
    title: str,
    url: str,
) -> None:
    clean_url = str(url or "").strip().rstrip(".,")
    parsed = urlsplit(clean_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or clean_url in seen:
        return
    seen.add(clean_url)
    candidates.append((" ".join(str(title or parsed.netloc).split())[:300], clean_url))


def candidate_row(
    *,
    title: str,
    url: str,
    source_id: str,
    query_intent: str,
    rank: int,
    request_id: str,
) -> dict[str, Any]:
    host = urlsplit(url).netloc.lower().removeprefix("www.")
    return {
        "source_id": source_id,
        "connector": AnySearchConnector.connector_id,
        "title": title,
        "url": url,
        "final_url": "",
        "publisher": host,
        "captured_at": utc_now(),
        "text": "",
        "source_kind": "discovery_candidate",
        "source_class": "discovery_only",
        "authority": "candidate_url_only",
        "access_mode": "anysearch_public_search",
        "discovered_via": "anysearch_search",
        "query_intent": query_intent,
        "provider_rank": rank,
        "provider_request_id": request_id,
        "is_final_page": False,
        "current_status": "unknown",
        "source_confidence": "medium",
    }
