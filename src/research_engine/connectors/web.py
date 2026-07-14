"""Public web-page connector."""

from __future__ import annotations

from html.parser import HTMLParser
import ipaddress
import re
import socket
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from research_engine.models import CollectionRequest, CollectionResult, utc_now


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
            body_status = "empty"
            try:
                if request.source_id == "target_discovery_refetch":
                    text, final_url, body_status = fetch_page_with_status(url)
                else:
                    text = fetch_text(url)
                    final_url = url if text.strip() else ""
            except Exception as exc:
                warnings.append(
                    f"web_page failed for {safe_url_for_warning(url)}: {type(exc).__name__}: {exc}"
                )
                continue
            metadata_keys = (
                "company",
                "source_kind",
                "source_class",
                "access_mode",
                "discovered_via",
                "discovery_source_id",
                "published_at",
                "author",
                "location",
                "current_status",
            )
            row = {key: page[key] for key in metadata_keys if key in page}
            if body_status == "empty" and text:
                body_status = page_body_status(text)
            is_usable = body_status == "usable"
            page_heading, target_detail = extract_target_detail(text)
            evidence_text = bounded_text_sample(target_detail or text)
            explicit_status = str(page.get("current_status") or "unknown")
            current_status = explicit_status
            status_inferred_from = ""
            if body_status == "not_found_or_closed":
                current_status = "closed"
            elif (
                is_usable
                and explicit_status == "unknown"
                and page.get("company")
                and page.get("source_kind") == "official_job_posting"
                and final_url
            ):
                inferred_status = infer_job_status(target_detail or text)
                if inferred_status != "unknown":
                    current_status = inferred_status
                    status_inferred_from = (
                        "full_target_detail" if target_detail else "full_fetched_body"
                    )
            row.update(
                {
                    "source_id": request.source_id,
                    "connector": self.connector_id,
                    "title": str(page.get("title") or url),
                    "url": url,
                    "final_url": final_url,
                    "publisher": str(page.get("publisher") or ""),
                    "captured_at": utc_now(),
                    "text": evidence_text,
                    "source_confidence": str(page.get("source_confidence") or "medium"),
                    "is_final_page": bool(is_usable and final_url),
                    "access_blocked": body_status == "access_blocked" or not bool(text.strip()),
                    "fetch_status": body_status,
                    "current_status": current_status,
                }
            )
            if page_heading:
                row["page_heading"] = page_heading
            if target_detail:
                row["target_detail_text"] = evidence_text
            if status_inferred_from:
                row["status_inferred_from"] = status_inferred_from
            rows.append(row)
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=rows,
            warnings=warnings,
        )


def fetch_text(url: str, *, timeout: float = 12.0) -> str:
    return fetch_page(url, timeout=timeout)[0]


def bounded_text_sample(text: str, *, limit: int = EVIDENCE_TEXT_CHARS) -> str:
    normalized = str(text or "")
    if len(normalized) <= limit:
        return normalized
    separator = "\n... [bounded middle omitted] ...\n"
    head_chars = (limit - len(separator)) // 2
    tail_chars = limit - len(separator) - head_chars
    return normalized[:head_chars] + separator + normalized[-tail_chars:]


def extract_target_detail(text: str) -> tuple[str, str]:
    """Extract a repeated document-title region from search-shell job pages."""
    value = str(text or "")
    title_match = re.match(
        r"^(.{3,240}?)\s+[—–-]\s+[^—–]{0,100}?careers\b",
        value,
        flags=re.IGNORECASE,
    )
    if not title_match:
        return "", ""
    heading = " ".join(title_match.group(1).split())
    positions = [match.start() for match in re.finditer(re.escape(heading), value, re.IGNORECASE)]
    if len(positions) < 2:
        return heading, ""
    return heading, value[positions[-1] :]


def infer_job_status(text: str) -> str:
    normalized = " ".join(str(text or "").lower().split())
    closed_markers = (
        "job is no longer available",
        "position has been filled",
        "job has expired",
        "no longer accepting applications",
    )
    if any(marker in normalized for marker in closed_markers):
        return "closed"
    jd_markers = (
        "responsibilities",
        "qualifications",
        "requirements",
        "what you'll do",
        "what you’ll do",
    )
    if any(marker in normalized for marker in jd_markers) and re.search(
        r"\b(apply|submit application)\b", normalized
    ):
        return "active"
    return "unknown"


def fetch_page(url: str, *, timeout: float = 12.0) -> tuple[str, str]:
    text, final_url, status = fetch_page_with_status(url, timeout=timeout)
    if status == "usable":
        return text, final_url
    return "", ""


def fetch_page_with_status(
    url: str, *, timeout: float = 12.0
) -> tuple[str, str, str]:
    validate_public_url(url)
    ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    request = Request(url, headers={"User-Agent": ua})
    initial_text = ""
    initial_url = ""
    initial_status = "empty"
    try:
        opener = build_opener(PublicRedirectHandler())
        with opener.open(request, timeout=timeout) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise ValueError(f"response body exceeds {MAX_RESPONSE_BYTES} byte limit")
            html = body.decode("utf-8", errors="replace")
            final_url = str(response.geturl() or url)
            validate_public_url(final_url)
        parser = _TextExtractor()
        parser.feed(html)
        initial_text = parser.text()[:MAX_TEXT_CHARS]
        initial_url = final_url
        initial_status = page_body_status(initial_text)
        if len(initial_text.strip()) >= 200 and initial_status == "usable":
            return initial_text, final_url, initial_status
    except ValueError:
        raise
    except Exception:
        pass
    text, final_url = _fetch_playwright(url, timeout=timeout)
    rendered_status = page_body_status(text)
    if text and rendered_status == "usable":
        return text, final_url, rendered_status
    if initial_text and initial_status == "usable":
        return initial_text, initial_url, initial_status
    if text:
        return text, final_url, rendered_status
    if initial_text:
        return initial_text, initial_url, initial_status
    return "", "", "empty"


def _fetch_playwright(url: str, *, timeout: float = 15.0) -> tuple[str, str]:
    """JS-rendered fallback using Playwright (optional dep)."""
    validate_public_url(url)
    try:
        import time
        from playwright.sync_api import sync_playwright  # type: ignore[import]

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            def guard_request(route, request) -> None:
                try:
                    validate_public_url(request.url)
                except ValueError:
                    route.abort()
                    return
                route.continue_()

            page.route("**/*", guard_request)
            page.goto(url, timeout=int(timeout * 1000))
            time.sleep(2)
            final_url = str(page.url or url)
            validate_public_url(final_url)
            text = page.inner_text("body")[:MAX_TEXT_CHARS]
            browser.close()
            return " ".join(text.split()), final_url
    except ValueError:
        raise
    except Exception:
        return "", ""


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
