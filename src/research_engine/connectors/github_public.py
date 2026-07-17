"""Unauthenticated GitHub repository search connector."""

from __future__ import annotations

import json
import os
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from research_engine.models import CollectionRequest, CollectionResult, utc_now
from research_engine.relevance import rank_github_repositories
from research_engine.security import sanitize_for_artifact


GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"


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
            row_from_repository(item, request=request, query=query, raw_api_rank=index)
            for index, item in enumerate(items[:max_results], start=1)
            if isinstance(item, dict)
        ]
        ranked = rank_github_repositories(
            [row for row in rows if row],
            query,
            as_of=request.run_date,
        )
        if request.depth == "audit" and request.source.get("enrich_github"):
            enrichment_limit = min(
                max(0, int(request.source.get("enrichment_limit") or 3)),
                3,
                len(ranked),
            )
            for row in ranked[:enrichment_limit]:
                try:
                    row["github_enrichment"] = enrich_github_repository(str(row.get("title") or ""))
                except Exception as exc:
                    warnings.append(
                        f"github enrichment failed for {row.get('title')}: {type(exc).__name__}"
                    )
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=ranked,
            warnings=warnings,
            metadata={
                "query": raw_query,
                "search_query": query,
                "total_count": payload.get("total_count") if isinstance(payload, dict) else None,
            },
        )


def fetch_github_repositories(query: str, *, max_results: int, timeout: float = 12.0) -> dict:
    request = build_github_request(query, max_results=max_results)
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def build_github_request(query: str, *, max_results: int) -> Request:
    """Build a best-match request; omitting ``sort`` preserves GitHub API rank."""

    params = urlencode({"q": query, "per_page": max(1, min(max_results, 20))})
    return Request(f"{GITHUB_SEARCH_URL}?{params}", headers=github_headers())


def github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "research-engine/0.2",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = str(os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


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
    raw_api_rank: int = 1,
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
    license_value = safe_item.get("license") if isinstance(safe_item.get("license"), dict) else {}
    license_spdx = str(license_value.get("spdx_id") or "")
    archived = bool(safe_item.get("archived", False))
    pushed_at = str(safe_item.get("pushed_at") or "")
    updated_at = str(safe_item.get("updated_at") or "")
    default_branch = str(safe_item.get("default_branch") or "")
    text_parts = [
        f"Repository: {full_name}",
        f"Description: {description}" if description else "",
        f"Language: {language}" if language else "",
        f"Stars: {stars}" if stars is not None else "",
        f"Forks: {forks}" if forks is not None else "",
        f"License: {license_spdx}" if license_spdx else "",
        f"Archived: {archived}",
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
        "updated_at": updated_at or pushed_at,
        "pushed_at": pushed_at,
        "captured_at": utc_now(),
        "query": query,
        "raw_api_rank": raw_api_rank,
        "text": text[:2000],
        "text_excerpt": text[:2000],
        "source_kind": "github_public_repository",
        "source_confidence": "medium_high",
        "access_mode": "public_github_api",
        "license_spdx": license_spdx,
        "archived": archived,
        "default_branch": default_branch,
        "topics": [str(topic) for topic in topics[:12]],
        "metrics": {
            "stars": stars,
            "forks": forks,
            "open_issues": safe_item.get("open_issues_count"),
            "language": language,
        },
    }


def enrich_github_repository(full_name: str, *, timeout: float = 12.0) -> dict:
    """Fetch a bounded release and contributor sample for one canonical repository."""

    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", full_name):
        raise ValueError("invalid GitHub repository name")
    base = f"https://api.github.com/repos/{full_name}"
    enrichment: dict[str, object] = {}
    try:
        release = fetch_github_json(f"{base}/releases/latest", timeout=timeout)
    except Exception:
        release = None
    if isinstance(release, dict):
        enrichment["latest_release"] = {
            "tag_name": str(release.get("tag_name") or ""),
            "name": str(release.get("name") or ""),
            "published_at": str(release.get("published_at") or ""),
            "url": str(release.get("html_url") or ""),
        }
    contributors = fetch_github_json(f"{base}/contributors?per_page=5&anon=1", timeout=timeout)
    if isinstance(contributors, list):
        enrichment["contributors"] = [
            str(item.get("login") or item.get("name") or "")
            for item in contributors[:5]
            if isinstance(item, dict) and (item.get("login") or item.get("name"))
        ]
    return sanitize_for_artifact(enrichment)


def fetch_github_json(url: str, *, timeout: float) -> object:
    with urlopen(Request(url, headers=github_headers()), timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))
