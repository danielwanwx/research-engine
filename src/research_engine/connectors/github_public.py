"""Unauthenticated GitHub repository search connector."""

from __future__ import annotations

import json
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from research_engine.models import CollectionRequest, CollectionResult, utc_now
from research_engine.security import sanitize_for_artifact


class GitHubPublicSearchConnector:
    connector_id = "github_public_search"

    def collect(self, request: CollectionRequest) -> CollectionResult:
        raw_query = str(request.source.get("query") or request.topic)
        query = normalize_github_query(raw_query)
        max_results = int(request.max_results or request.source.get("max_results") or 5)
        warnings: list[str] = []
        try:
            payload = fetch_github_repositories(query, max_results=max_results)
        except Exception as exc:
            warnings.append(f"github_public_search failed: {type(exc).__name__}")
            return CollectionResult(
                source_id=request.source_id,
                connector=self.connector_id,
                rows=[],
                warnings=warnings,
            )
        items = payload.get("items") if isinstance(payload, dict) else []
        rows = [
            row_from_repository(item, request=request, query=query)
            for item in items[:max_results]
            if isinstance(item, dict)
        ]
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=[row for row in rows if row],
            warnings=warnings,
            metadata={
                "query": raw_query,
                "search_query": query,
                "total_count": payload.get("total_count") if isinstance(payload, dict) else None,
            },
        )


def fetch_github_repositories(query: str, *, max_results: int, timeout: float = 12.0) -> dict:
    params = urlencode(
        {
            "q": query,
            "sort": "updated",
            "order": "desc",
            "per_page": max(1, min(max_results, 20)),
        }
    )
    request = Request(
        f"https://api.github.com/search/repositories?{params}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "research-engine/0.1",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def normalize_github_query(query: str) -> str:
    text = re.sub(r"#(?=\w)", "", query)
    text = re.sub(r"\b(github|open source|repo|repositories)\b", " ", text, flags=re.IGNORECASE)
    text = " ".join(text.split())
    return text or query


def row_from_repository(
    item: dict,
    *,
    request: CollectionRequest,
    query: str,
) -> dict:
    safe_item = sanitize_for_artifact(item)
    if not isinstance(safe_item, dict):
        safe_item = {}
    owner = safe_item.get("owner") if isinstance(safe_item.get("owner"), dict) else {}
    full_name = str(safe_item.get("full_name") or safe_item.get("name") or "")
    url = str(safe_item.get("html_url") or "")
    description = str(safe_item.get("description") or "")
    topics = safe_item.get("topics") if isinstance(safe_item.get("topics"), list) else []
    stars = safe_item.get("stargazers_count")
    forks = safe_item.get("forks_count")
    language = safe_item.get("language")
    text_parts = [
        f"Repository: {full_name}",
        f"Description: {description}" if description else "",
        f"Language: {language}" if language else "",
        f"Stars: {stars}" if stars is not None else "",
        f"Forks: {forks}" if forks is not None else "",
        "Topics: " + ", ".join(str(topic) for topic in topics[:12]) if topics else "",
    ]
    text = " ".join(part for part in text_parts if part)
    return {
        "source_id": request.source_id,
        "connector": GitHubPublicSearchConnector.connector_id,
        "platform": "github",
        "title": full_name or url or "GitHub repository result",
        "url": url,
        "author": str(owner.get("login") or ""),
        "published_at": str(safe_item.get("created_at") or ""),
        "updated_at": str(safe_item.get("updated_at") or safe_item.get("pushed_at") or ""),
        "captured_at": utc_now(),
        "query": query,
        "text": text[:2000],
        "text_excerpt": text[:2000],
        "source_kind": "github_public_repository",
        "source_confidence": "medium_high",
        "access_mode": "public_github_api",
        "metrics": {
            "stars": stars,
            "forks": forks,
            "open_issues": safe_item.get("open_issues_count"),
            "language": language,
        },
    }
