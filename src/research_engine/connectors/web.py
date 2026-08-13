"""Public web-page connector."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from html.parser import HTMLParser
import ipaddress
import socket
import threading
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser

from research_engine.models import CollectionRequest, CollectionResult, utc_now
from research_engine.network_errors import raise_if_transient_network_error
from research_engine.extraction import extract_content
from research_engine.freshness import extract_temporal_metadata
from research_engine.quality import evidence_invalid_reasons


MAX_RESPONSE_BYTES = 2_000_000
MAX_TEXT_CHARS = 100_000
BLOCKED_HOST_SUFFIXES = (".localhost", ".local", ".internal")
HONEST_USER_AGENT = "research-engine/0.2"
MAX_ROBOTS_BYTES = 512_000


@dataclass(frozen=True)
class FetchedPage:
    text: str
    final_url: str
    http_status: int | None
    content_type: str
    content_valid: bool
    content_invalid_reasons: tuple[str, ...]
    content_blocks: tuple[dict[str, str], ...] = ()
    tables: tuple[Any, ...] = ()
    structured_data: Any = None
    extraction_warnings: tuple[str, ...] = ()
    published_at: str = ""
    date_source: str = ""
    date_confidence: str = ""
    updated_at: str = ""
    updated_date_source: str = ""
    updated_date_confidence: str = ""
    observed_at: str = ""
    observed_date_source: str = ""
    observed_date_confidence: str = ""
    extracted_content: bool = False
    network_status: str = "ok"
    network_telemetry: dict[str, Any] = field(default_factory=dict)


class RobotsPolicy:
    """Host-scoped robots policy with injectable transport and cached decisions."""

    def __init__(
        self,
        *,
        fetcher: Callable[[str, float], str] | None = None,
        user_agent: str = HONEST_USER_AGENT,
    ) -> None:
        self.fetcher = fetcher
        self.user_agent = user_agent
        self._cache: dict[str, tuple[RobotFileParser | None, str]] = {}
        self._lock = threading.Lock()

    def check(self, url: str, *, timeout: float, opener: Any | None = None) -> dict[str, Any]:
        parsed = urlsplit(url)
        robots_url = urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))
        with self._lock:
            cached = self._cache.get(robots_url)
        cache_hit = cached is not None
        if cached is None:
            parser, status = self._load(robots_url, timeout=timeout, opener=opener)
            with self._lock:
                self._cache[robots_url] = (parser, status)
        else:
            parser, status = cached
        allowed = (
            parser.can_fetch(self.user_agent, url)
            if parser
            else status not in {"denied", "rate_limit"}
        )
        decision_status = ("allowed" if allowed else "denied") if status == "loaded" else status
        return {
            "robots_url": robots_url,
            "robots_status": decision_status,
            "robots_allowed": allowed,
            "robots_cache_hit": cache_hit,
            "user_agent": self.user_agent,
        }

    def _load(
        self,
        robots_url: str,
        *,
        timeout: float,
        opener: Any | None,
    ) -> tuple[RobotFileParser | None, str]:
        try:
            text = (
                self.fetcher(robots_url, timeout)
                if self.fetcher
                else fetch_robots_text(robots_url, timeout=timeout, opener=opener)
            )
        except HTTPError as exc:
            if exc.code in {401, 403}:
                return None, "denied"
            if exc.code == 404:
                return None, "not_found"
            if exc.code == 429:
                return None, "rate_limit"
            return None, "unavailable"
        except Exception:
            return None, "unavailable"
        parser = RobotFileParser(robots_url)
        parser.parse(str(text).splitlines())
        return parser, "loaded"


DEFAULT_ROBOTS_POLICY = RobotsPolicy()


MAX_RESPONSE_BYTES = 2_000_000
MAX_TEXT_CHARS = 100_000
EVIDENCE_TEXT_CHARS = 4_000
BLOCKED_HOST_SUFFIXES = (".localhost", ".local", ".internal")


def page_body_status(text: str) -> str:
    """Classify fetched bodies that cannot be treated as final evidence."""
    normalized = " ".join(str(text or "").lower().replace("…", " ").split())
    if not normalized:
        return "empty"

    if (
        "you've been blocked by network security" in normalized
        or "you’ve been blocked by network security" in normalized
        or (
            "403 error" in normalized
            and ("request blocked" in normalized or "cloudfront" in normalized)
        )
        or (
            "the request could not be satisfied" in normalized
            and "cloudfront" in normalized
        )
    ):
        return "access_blocked"

    if len(normalized) <= 2_000 and any(
        marker in normalized
        for marker in (
            "verify you are human",
            "access denied",
            "cf-browser-verification",
            "captcha challenge",
        )
    ):
        return "access_blocked"

    if any(
        marker in normalized
        for marker in (
            "page not found",
            "404 not found",
            "job not found",
            "job is no longer available",
            "job posting is no longer available",
            "job posting has expired",
            "position has been filled",
            "position has been closed",
            "no longer accepting applications",
        )
    ):
        return "not_found_or_closed"

    if len(normalized) <= 500 and (
        (normalized.startswith("loading") and "powered by" in normalized)
        or "enable javascript to view this page" in normalized
        or "please enable javascript to continue" in normalized
    ):
        return "javascript_shell"
    return "usable"


class PublicRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if text and not self._skip_depth:
            self.parts.append(text)

    def text(self) -> str:
        return " ".join(self.parts)


class WebPageConnector:
    connector_id = "web_page"

    def __init__(
        self,
        *,
        fetcher: Callable[[str], FetchedPage] | None = None,
        robots_policy: RobotsPolicy | None = None,
    ) -> None:
        self.fetcher = fetcher
        self.robots_policy = robots_policy or DEFAULT_ROBOTS_POLICY

    def collect(self, request: CollectionRequest) -> CollectionResult:
        rows: list[dict] = []
        warnings: list[str] = []
        pages = request.source.get("pages") or []
        for page in pages[: request.max_results]:
            if not isinstance(page, dict):
                continue
            url = str(page.get("url") or "")
            if not url:
                continue
            try:
                fetched = (
                    self.fetcher(url)
                    if self.fetcher
                    else fetch_page_result(url, robots_policy=self.robots_policy)
                )
            except Exception as exc:
                raise_if_transient_network_error(exc)
                warnings.append(
                    f"web_page failed for {safe_url_for_warning(url)}: {type(exc).__name__}: {exc}"
                )
                continue
            if not fetched.content_valid:
                warnings.append(
                    "web_page invalid content for "
                    f"{safe_url_for_warning(url)}: {','.join(fetched.content_invalid_reasons)}"
                )
            metadata_keys = (
                "company",
                "source_kind",
                "source_class",
                "access_mode",
                "discovered_via",
                "discovery_source_id",
                "query_id",
                "facet_id",
                "published_at",
                "updated_at",
                "observed_at",
                "author",
                "location",
            )
            row = {key: page[key] for key in metadata_keys if key in page}
            row.update(
                {
                    "source_id": request.source_id,
                    "connector": self.connector_id,
                    "title": str(page.get("title") or url),
                    "url": url,
                    "final_url": fetched.final_url,
                    "publisher": str(page.get("publisher") or ""),
                    "captured_at": utc_now(),
                    "text": fetched.text[:4000],
                    "source_confidence": str(page.get("source_confidence") or "medium"),
                    "http_status": fetched.http_status,
                    "content_type": fetched.content_type,
                    "content_valid": fetched.content_valid,
                    "content_invalid": not fetched.content_valid,
                    "content_invalid_reasons": list(fetched.content_invalid_reasons),
                    "content_blocks": [dict(block) for block in fetched.content_blocks],
                    "tables": list(fetched.tables),
                    "structured_data": fetched.structured_data,
                    "extraction_warnings": list(fetched.extraction_warnings),
                    "published_at": str(page.get("published_at") or fetched.published_at),
                    "date_source": str(page.get("date_source") or fetched.date_source),
                    "date_confidence": str(
                        page.get("date_confidence") or fetched.date_confidence
                    ),
                    "updated_at": str(page.get("updated_at") or fetched.updated_at),
                    "updated_date_source": str(
                        page.get("updated_date_source") or fetched.updated_date_source
                    ),
                    "updated_date_confidence": str(
                        page.get("updated_date_confidence") or fetched.updated_date_confidence
                    ),
                    "observed_at": str(page.get("observed_at") or fetched.observed_at),
                    "observed_date_source": str(
                        page.get("observed_date_source") or fetched.observed_date_source
                    ),
                    "observed_date_confidence": str(
                        page.get("observed_date_confidence") or fetched.observed_date_confidence
                    ),
                    "extracted_content": fetched.extracted_content,
                    "network_status": fetched.network_status,
                    "network_telemetry": dict(fetched.network_telemetry),
                    "is_final_page": fetched.content_valid,
                    "access_blocked": any(
                        reason
                        in {
                            "access_blocked",
                            "access_denied",
                            "blocked_by_network_security",
                            "browser_verification",
                            "captcha",
                            "enable_javascript",
                            "human_verification",
                            "login_wall",
                            "robots_denied",
                            "security_check",
                            "unusual_traffic",
                        }
                        for reason in fetched.content_invalid_reasons
                    ),
                }
            )
            rows.append(row)
        network_statuses = [str(row.get("network_status") or "ok") for row in rows]
        status = next(
            (
                candidate
                for candidate in ("rate_limit", "robots_denied", "retry_exhausted")
                if candidate in network_statuses
            ),
            "ready" if rows else "empty",
        )
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=rows,
            warnings=warnings,
            metadata={
                "status": status,
                "network_status_counts": {
                    value: network_statuses.count(value) for value in sorted(set(network_statuses))
                },
            },
        )


def fetch_text(url: str, *, timeout: float = 12.0) -> str:
    return fetch_page(url, timeout=timeout)[0]


def fetch_page(url: str, *, timeout: float = 12.0) -> tuple[str, str]:
    fetched = fetch_page_result(url, timeout=timeout)
    if not fetched.content_valid:
        return "", ""
    return fetched.text, fetched.final_url


def fetch_page_result(
    url: str,
    *,
    timeout: float = 12.0,
    opener: Any | None = None,
    rendered_fetcher: Callable[..., FetchedPage | None] | None = None,
    robots_policy: RobotsPolicy | None = None,
) -> FetchedPage:
    validate_public_url(url)
    resolved_opener = opener or build_opener(PublicRedirectHandler())
    policy = robots_policy or DEFAULT_ROBOTS_POLICY
    robots = policy.check(url, timeout=timeout, opener=resolved_opener)
    if not robots["robots_allowed"]:
        network_status = (
            "rate_limit" if robots["robots_status"] == "rate_limit" else "robots_denied"
        )
        return FetchedPage(
            text="",
            final_url=url,
            http_status=None,
            content_type="",
            content_valid=False,
            content_invalid_reasons=(network_status,),
            network_status=network_status,
            network_telemetry=robots,
        )
    request = Request(url, headers={"User-Agent": HONEST_USER_AGENT})
    initial: FetchedPage | None = None
    try:
        with resolved_opener.open(request, timeout=timeout) as response:
            body = _read_body(response)
            final_url = str(response.geturl() or url)
            validate_public_url(final_url)
            initial = _make_fetched_page(
                body=body,
                final_url=final_url,
                http_status=_response_status(response),
                content_type=_response_content_type(response),
                network_telemetry=robots,
            )
    except HTTPError as exc:
        body = _read_body(exc)
        final_url = str(exc.geturl() or url)
        validate_public_url(final_url)
        return _make_fetched_page(
            body=body,
            final_url=final_url,
            http_status=int(exc.code),
            content_type=_response_content_type(exc),
            network_status="rate_limit" if exc.code == 429 else "http_error",
            network_telemetry={**robots, **retry_after_telemetry(exc)},
        )
    except ValueError:
        raise
    except Exception:
        rendered = (rendered_fetcher or _fetch_playwright_result)(url, timeout=timeout)
        if rendered:
            return replace(rendered, network_telemetry=robots)
        return _make_fetched_page(
            body=b"",
            final_url="",
            http_status=None,
            content_type="",
            extra_reasons=("transport_error",),
            network_status="retry_exhausted",
            network_telemetry=robots,
        )

    if initial.content_valid and len(initial.text) >= 200:
        return initial
    if initial.http_status is not None and initial.http_status >= 400:
        return initial
    if any(reason.startswith("unsupported_content_type_") for reason in initial.content_invalid_reasons):
        return initial

    rendered = (rendered_fetcher or _fetch_playwright_result)(url, timeout=timeout)
    if rendered:
        rendered = replace(rendered, network_telemetry=robots)
    if rendered and rendered.content_valid:
        return rendered
    if initial.content_valid:
        return initial
    if rendered and len(rendered.text) > len(initial.text):
        return rendered
    return initial


def _read_body(response: Any) -> bytes:
    body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise ValueError(f"response body exceeds {MAX_RESPONSE_BYTES} byte limit")
    return body


def fetch_robots_text(url: str, *, timeout: float, opener: Any | None = None) -> str:
    validate_public_url(url)
    request = Request(url, headers={"User-Agent": HONEST_USER_AGENT})
    resolved_opener = opener or build_opener(PublicRedirectHandler())
    with resolved_opener.open(request, timeout=timeout) as response:
        final_url = str(response.geturl() or url)
        validate_public_url(final_url)
        body = response.read(MAX_ROBOTS_BYTES + 1)
    if len(body) > MAX_ROBOTS_BYTES:
        raise ValueError("robots response exceeds byte limit")
    return body.decode("utf-8", errors="replace")


def retry_after_telemetry(exc: HTTPError) -> dict[str, Any]:
    headers = getattr(exc, "headers", None)
    value = headers.get("Retry-After") if hasattr(headers, "get") else None
    try:
        seconds = max(0.0, float(value))
    except (TypeError, ValueError):
        return {}
    return {"retry_after_seconds": seconds}


def _response_status(response: Any) -> int | None:
    status = getattr(response, "status", None)
    if status is None and hasattr(response, "getcode"):
        status = response.getcode()
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


def _response_content_type(response: Any) -> str:
    headers = getattr(response, "headers", None)
    if headers is None:
        return ""
    if hasattr(headers, "get_content_type"):
        return str(headers.get_content_type() or "").lower()
    if hasattr(headers, "get"):
        return str(headers.get("content-type") or headers.get("Content-Type") or "").lower()
    return ""


def _make_fetched_page(
    *,
    body: bytes,
    final_url: str,
    http_status: int | None,
    content_type: str,
    extra_reasons: tuple[str, ...] = (),
    network_status: str = "ok",
    network_telemetry: dict[str, Any] | None = None,
) -> FetchedPage:
    normalized_type = content_type.split(";", 1)[0].strip().lower()
    if not normalized_type:
        sample = body[:2048].lower()
        normalized_type = (
            "text/html" if b"<html" in sample or b"<body" in sample else "text/plain"
        )
    extraction = extract_content(
        body,
        content_type=normalized_type,
        parent_evidence_id="transport-page",
        max_bytes=MAX_RESPONSE_BYTES,
        chunk_chars=4_000,
    )
    text = str(extraction.get("text") or "")
    extraction_reasons = [str(reason) for reason in extraction.get("content_invalid_reasons") or []]
    compatibility_reasons: list[str] = []
    if normalized_type == "application/pdf" and extraction_reasons:
        compatibility_reasons.extend(("binary_pdf", "unsupported_content_type_application/pdf"))
    elif b"\x00" in body[:1024] and extraction_reasons:
        compatibility_reasons.append("binary_content")
    row = {
        "connector": "web_page",
        "text": text,
        "final_url": final_url,
        "http_status": http_status,
        "content_type": normalized_type,
        "extracted_content": bool(
            normalized_type == "application/pdf" and extraction.get("content_valid")
        ),
    }
    reasons = list(
        dict.fromkeys(
            [
                *extra_reasons,
                *compatibility_reasons,
                *extraction_reasons,
                *evidence_invalid_reasons(row),
            ]
        )
    )
    raw_html = body.decode("utf-8", errors="replace") if "html" in normalized_type else ""
    temporal = extract_temporal_metadata(
        {
            "raw_html": raw_html,
            "final_url": final_url,
            "tables": extraction.get("tables") or [],
        }
    )
    return FetchedPage(
        text=text[:MAX_TEXT_CHARS],
        final_url=final_url,
        http_status=http_status,
        content_type=normalized_type,
        content_valid=not reasons,
        content_invalid_reasons=tuple(reasons),
        content_blocks=tuple(dict(block) for block in extraction.get("blocks") or []),
        tables=tuple(extraction.get("tables") or []),
        structured_data=extraction.get("structured_data"),
        extraction_warnings=tuple(str(value) for value in extraction.get("warnings") or []),
        published_at=temporal["published_at"],
        date_source=temporal["date_source"],
        date_confidence=temporal["date_confidence"],
        updated_at=temporal["updated_at"],
        updated_date_source=temporal["updated_date_source"],
        updated_date_confidence=temporal["updated_date_confidence"],
        observed_at=temporal["observed_at"],
        observed_date_source=temporal["observed_date_source"],
        observed_date_confidence=temporal["observed_date_confidence"],
        extracted_content=bool(
            normalized_type == "application/pdf" and extraction.get("content_valid")
        ),
        network_status=network_status,
        network_telemetry=dict(network_telemetry or {}),
    )


def _extract_response_text(body: bytes, *, content_type: str) -> str:
    if content_type and not (
        content_type.startswith("text/")
        or content_type
        in {"application/json", "application/ld+json", "application/xhtml+xml", "application/xml"}
    ):
        return ""
    decoded = body.decode("utf-8", errors="replace")
    if "html" in content_type or "<html" in decoded.lower() or "<body" in decoded.lower():
        parser = _TextExtractor()
        parser.feed(decoded)
        return parser.text()[:MAX_TEXT_CHARS]
    return " ".join(decoded.split())[:MAX_TEXT_CHARS]


def _fetch_playwright_result(url: str, *, timeout: float = 15.0) -> FetchedPage | None:
    """JS-rendered fallback using Playwright (optional dep)."""
    validate_public_url(url)
    try:
        import time
        from playwright.sync_api import sync_playwright  # type: ignore[import]

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=HONEST_USER_AGENT)

            def guard_request(route, request) -> None:
                try:
                    validate_public_url(request.url)
                except ValueError:
                    route.abort()
                    return
                route.continue_()

            page.route("**/*", guard_request)
            response = page.goto(url, timeout=int(timeout * 1000))
            time.sleep(2)
            final_url = str(page.url or url)
            validate_public_url(final_url)
            text = page.inner_text("body")[:MAX_TEXT_CHARS]
            browser.close()
            headers = getattr(response, "headers", {}) if response else {}
            content_type = str(headers.get("content-type") or "text/html")
            return _make_fetched_page(
                body=" ".join(text.split()).encode("utf-8"),
                final_url=final_url,
                http_status=_response_status(response) if response else None,
                content_type=content_type,
            )
    except ValueError:
        raise
    except Exception:
        return None


def validate_public_url(url: str) -> str:
    parsed = urlsplit(str(url or "").strip())
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("URL scheme must be http or https")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL credentials are not allowed")
    host = str(parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise ValueError("URL must include a public host")
    if host == "localhost" or host.endswith(BLOCKED_HOST_SUFFIXES):
        raise ValueError("URL host is not public")
    try:
        literal = ipaddress.ip_address(host)
        addresses = [literal]
    except ValueError:
        try:
            records = socket.getaddrinfo(
                host,
                parsed.port or (443 if parsed.scheme.lower() == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        except OSError as exc:
            raise ValueError("URL host could not be resolved to a public address") from exc
        addresses = []
        for record in records:
            try:
                addresses.append(ipaddress.ip_address(record[4][0]))
            except ValueError:
                continue
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("URL host does not resolve exclusively to public addresses")
    return urlunsplit(parsed)


def safe_url_for_warning(url: str) -> str:
    parsed = urlsplit(str(url or ""))
    host = str(parsed.hostname or "")
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
