"""Public web-search discovery connector with explicit provider boundaries."""

from __future__ import annotations

import json
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from research_engine.models import CollectionRequest, CollectionResult, utc_now
from research_engine.network_errors import raise_if_transient_network_error
from research_engine.security import sanitize_for_artifact


ANYSEARCH_ENDPOINT = "https://api.anysearch.com/v1/search"
MAX_RESULTS = 20
Transport = Callable[[Request, float], Any]


class WebSearchConnector:
    """Return discovery candidates; snippets are never claim evidence."""

    connector_id = "web_search"

    def __init__(self, *, transport: Transport | None = None) -> None:
        self.transport = transport or fetch_json

    def collect(self, request: CollectionRequest) -> CollectionResult:
        provider = str(request.source.get("provider") or "anysearch").strip().lower()
        query = str(request.source.get("query") or request.topic).strip()
        limit = max(1, min(int(request.max_results or 5), MAX_RESULTS))
        if provider == "none":
            return self._result(request, provider=provider, query=query, status="disabled")
        if provider not in {"anysearch", "searxng"}:
            return self._result(
                request,
                provider=provider,
                query=query,
                status="failed",
                warnings=[f"web_search unsupported provider: {provider}"],
            )
        endpoint = str(request.source.get("endpoint") or "").strip()
        if provider == "searxng" and not endpoint:
            return self._result(
                request,
                provider=provider,
                query=query,
                status="failed",
                warnings=["web_search searxng requires an explicit endpoint"],
            )
        try:
            http_request = build_search_request(
                provider,
                query=query,
                limit=limit,
                endpoint=endpoint,
                source=request.source,
            )
            timeout = float(request.source.get("timeout_seconds") or 12.0)
            payload = self.transport(http_request, timeout)
            items, total = parse_provider_payload(provider, payload)
        except HTTPError as exc:
            return self._result(
                request,
                provider=provider,
                query=query,
                status="rate_limit" if exc.code == 429 else "failed",
                warnings=[f"web_search {provider} HTTP {exc.code}"],
            )
        except MalformedPayload:
            return self._result(
                request,
                provider=provider,
                query=query,
                status="failed",
                warnings=[f"web_search {provider} returned malformed payload"],
            )
        except ProviderError as exc:
            return self._result(
                request,
                provider=provider,
                query=query,
                status="rate_limit" if exc.safe_code == 429 else "failed",
                warnings=[f"web_search {provider} API error{exc.safe_suffix}"],
            )
        except Exception as exc:
            raise_if_transient_network_error(exc)
            return self._result(
                request,
                provider=provider,
                query=query,
                status="failed",
                warnings=[f"web_search {provider} failed: {type(exc).__name__}"],
            )

        rows = [
            row_from_result(item, request=request, provider=provider, query=query, raw_rank=index)
            for index, item in enumerate(items[:limit], start=1)
            if isinstance(item, dict)
        ]
        usable = [row for row in rows if row]
        return self._result(
            request,
            provider=provider,
            query=query,
            status="ready" if usable else "empty",
            rows=usable,
            total=total,
        )

    def _result(
        self,
        request: CollectionRequest,
        *,
        provider: str,
        query: str,
        status: str,
        rows: list[dict[str, Any]] | None = None,
        warnings: list[str] | None = None,
        total: Any = None,
    ) -> CollectionResult:
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=rows or [],
            warnings=warnings or [],
            metadata={
                "status": status,
                "provider": provider,
                "query": query,
                "third_party_query_boundary": provider not in {"none", ""},
                "total_count": total,
            },
        )


class MalformedPayload(ValueError):
    pass


class ProviderError(ValueError):
    def __init__(self, code: Any) -> None:
        self.safe_code = code if isinstance(code, int) else None
        self.safe_suffix = f" code {code}" if isinstance(code, int) else ""


def build_search_request(
    provider: str,
    *,
    query: str,
    limit: int,
    endpoint: str,
    source: dict[str, Any],
) -> Request:
    if provider == "anysearch":
        payload: dict[str, Any] = {"query": query[:2000], "limit": limit}
        for key in ("zone", "language", "tag"):
            if source.get(key) is not None and source.get(key) != "":
                payload[key] = str(source[key])[:100]
        if isinstance(source.get("params"), dict):
            payload["params"] = bounded_params(source["params"])
        return Request(
            ANYSEARCH_ENDPOINT,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "research-engine/0.2",
            },
            method="POST",
        )
    _validate_endpoint(endpoint)
    parsed = urlsplit(endpoint)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    params.update({"q": query, "format": "json"})
    language = str(source.get("language") or "").strip()
    if language:
        params["language"] = language
    url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/search", urlencode(params), ""))
    return Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "research-engine/0.2"},
    )


def _validate_endpoint(endpoint: str) -> None:
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("SearXNG endpoint must be HTTP(S)")
    if parsed.username or parsed.password:
        raise ValueError("SearXNG endpoint must not contain credentials")


def bounded_params(params: dict[str, Any]) -> dict[str, Any]:
    safe = sanitize_for_artifact(params)
    if not isinstance(safe, dict):
        return {}
    bounded: dict[str, Any] = {}
    for key, value in list(safe.items())[:20]:
        if isinstance(value, (bool, int, float)) or value is None:
            bounded[str(key)[:100]] = value
        elif isinstance(value, str):
            bounded[str(key)[:100]] = value[:500]
    return bounded


def fetch_json(request: Request, timeout: float) -> Any:
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def parse_provider_payload(provider: str, payload: Any) -> tuple[list[Any], Any]:
    if not isinstance(payload, dict):
        raise MalformedPayload
    if provider == "anysearch":
        data = payload.get("data")
        if payload.get("code") != 0:
            raise ProviderError(payload.get("code"))
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            raise MalformedPayload
        return data["results"], data.get("total") or data.get("total_count")
    if not isinstance(payload.get("results"), list):
        raise MalformedPayload
    return payload["results"], payload.get("number_of_results")


def row_from_result(
    item: dict[str, Any],
    *,
    request: CollectionRequest,
    provider: str,
    query: str,
    raw_rank: int,
) -> dict[str, Any]:
    safe = sanitize_for_artifact(item)
    if not isinstance(safe, dict):
        return {}
    url = str(safe.get("url") or safe.get("link") or "").strip()
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return {}
    title = str(safe.get("title") or url).strip()
    snippet = str(safe.get("snippet") or safe.get("content") or safe.get("description") or "").strip()
    return {
        "source_id": request.source_id,
        "connector": WebSearchConnector.connector_id,
        "title": title[:500],
        "url": url,
        "final_url": "",
        "publisher": parsed.netloc.lower().removeprefix("www."),
        "captured_at": utc_now(),
        "query": query,
        "query_id": str(request.source.get("query_id") or ""),
        "facet_id": str(request.source.get("facet_id") or ""),
        "raw_provider_rank": raw_rank,
        "text": snippet[:2000],
        "text_excerpt": snippet[:2000],
        "source_kind": "web_search_result",
        "source_class": "discovery_only",
        "claim_eligible": False,
        "access_mode": f"public_{provider}_search",
        "discovered_via": provider,
        "is_final_page": False,
        "source_confidence": "low",
    }
