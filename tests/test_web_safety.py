import pytest
from urllib.error import HTTPError

from research_engine.connectors import web


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/private",
        "http://localhost/private",
        "http://169.254.169.254/latest/meta-data",
        "http://user:password@example.com/private",
        "file:///etc/passwd",
    ],
)
def test_fetch_page_rejects_non_public_or_credentialed_urls_before_transport(url):
    with pytest.raises(ValueError, match="public|credentials|scheme"):
        web.fetch_page(url)


def test_redirect_handler_rejects_private_redirect_before_following():
    handler = web.PublicRedirectHandler()

    with pytest.raises(ValueError, match="public"):
        handler.redirect_request(
            None,
            None,
            302,
            "Found",
            {},
            "http://127.0.0.1/private",
        )


class FakeResponse:
    def __init__(
        self,
        *,
        body: bytes,
        final_url: str,
        status: int = 200,
        content_type: str = "text/html",
    ):
        self.body = body
        self.final_url = final_url
        self.status = status
        self.headers = {"content-type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, limit):
        return self.body[:limit]

    def geturl(self):
        return self.final_url

    def close(self):
        return None


class FakeOpener:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        return self.response


def test_fetch_page_bounds_response_body(monkeypatch):
    response = FakeResponse(
        body=b"x" * (web.MAX_RESPONSE_BYTES + 1),
        final_url="https://93.184.216.34/job/123",
    )
    monkeypatch.setattr(web, "build_opener", lambda *handlers: FakeOpener(response))

    with pytest.raises(ValueError, match="response body exceeds"):
        web.fetch_page("https://93.184.216.34/job/123")


def test_fetch_page_revalidates_final_redirect_url(monkeypatch):
    response = FakeResponse(
        body=b"<html><body>public start</body></html>",
        final_url="http://127.0.0.1/private",
    )
    monkeypatch.setattr(web, "build_opener", lambda *handlers: FakeOpener(response))

    with pytest.raises(ValueError, match="public"):
        web.fetch_page("https://93.184.216.34/start")


@pytest.mark.parametrize(
    ("body", "status", "content_type", "expected_reason"),
    [
        (b"%PDF-1.7 binary data", 200, "application/pdf", "unsupported_content_type_application/pdf"),
        (
            b"<html><body>This page does not exist but has a long explanatory body for users.</body></html>",
            404,
            "text/html",
            "http_status_404",
        ),
    ],
)
def test_fetch_page_result_quarantines_status_and_binary_failures(
    monkeypatch,
    body,
    status,
    content_type,
    expected_reason,
):
    response = FakeResponse(
        body=body,
        final_url="https://93.184.216.34/probe",
        status=status,
        content_type=content_type,
    )
    monkeypatch.setattr(web, "build_opener", lambda *handlers: FakeOpener(response))

    result = web.fetch_page_result("https://93.184.216.34/probe")

    assert result.content_valid is False
    assert expected_reason in result.content_invalid_reasons


def test_fetch_page_result_quarantines_login_wall(monkeypatch):
    response = FakeResponse(
        body=(
            b"<html><body>Log in to X. Continue with Google. "
            b"Create an account to see posts and conversations.</body></html>"
        ),
        final_url="https://93.184.216.34/login",
    )
    monkeypatch.setattr(web, "build_opener", lambda *handlers: FakeOpener(response))
    monkeypatch.setattr(web, "_fetch_playwright_result", lambda *args, **kwargs: None)

    result = web.fetch_page_result("https://93.184.216.34/login")

    assert result.content_valid is False
    assert "login_wall" in result.content_invalid_reasons
    assert web.fetch_page("https://93.184.216.34/login") == ("", "")


def test_invalid_rendered_page_cannot_replace_valid_static_content():
    static_text = (
        "This valid static article contains enough evidence and context to pass the minimum "
        "content threshold, but remains shorter than the browser fallback threshold."
    )
    response = FakeResponse(
        body=f"<html><body>{static_text}</body></html>".encode(),
        final_url="https://93.184.216.34/article",
    )
    rendered = web.FetchedPage(
        text=("Sign in to GitHub to continue. " * 20),
        final_url="https://93.184.216.34/login",
        http_status=200,
        content_type="text/html",
        content_valid=False,
        content_invalid_reasons=("login_wall",),
    )

    result = web.fetch_page_result(
        "https://93.184.216.34/article",
        opener=FakeOpener(response),
        rendered_fetcher=lambda *args, **kwargs: rendered,
    )

    assert result.content_valid is True
    assert result.text == static_text


def test_fetch_page_preserves_semantic_blocks_tables_and_structured_date(monkeypatch):
    response = FakeResponse(
        body=(
            b'<html><head><meta property="article:published_time" content="2026-07-10">'
            b'</head><body><h1>Market table</h1><p>Primary evidence paragraph with enough '
            b'content to pass the transport validity threshold for this page.</p>'
            b'<table><tr><th>Vendor</th><th>Product</th></tr>'
            b'<tr><td>Micron</td><td>HBM3E</td></tr></table></body></html>'
        ),
        final_url="https://93.184.216.34/report",
    )
    monkeypatch.setattr(web, "build_opener", lambda *handlers: FakeOpener(response))

    result = web.fetch_page_result("https://93.184.216.34/report")

    assert result.content_valid is True
    assert result.content_blocks
    assert result.tables == ([
        ["Vendor", "Product"],
        ["Micron", "HBM3E"],
    ],)
    assert result.published_at == "2026-07-10"
    assert result.date_source == "html_meta"


def test_fetch_page_uses_honest_research_engine_user_agent():
    response = FakeResponse(
        body=b"<html><body>A sufficiently detailed public technical article for evidence.</body></html>",
        final_url="https://93.184.216.34/article",
    )
    opener = FakeOpener(response)

    web.fetch_page_result(
        "https://93.184.216.34/article",
        opener=opener,
        rendered_fetcher=lambda *args, **kwargs: None,
    )

    assert opener.requests[0].get_header("User-agent").startswith("research-engine/")
    assert "Mozilla" not in opener.requests[0].get_header("User-agent")


def test_robots_denial_prevents_page_transport_and_is_cached():
    robots_fetches = []

    def fetch_robots(url, timeout):
        robots_fetches.append(url)
        return "User-agent: *\nDisallow: /private\n"

    policy = web.RobotsPolicy(fetcher=fetch_robots)
    page_transport_calls = []

    class FailingOpener:
        def open(self, request, timeout):
            page_transport_calls.append(request.full_url)
            raise AssertionError("denied page must not be fetched")

    first = web.fetch_page_result(
        "https://93.184.216.34/private/report",
        opener=FailingOpener(),
        robots_policy=policy,
    )
    second = web.fetch_page_result(
        "https://93.184.216.34/private/other",
        opener=FailingOpener(),
        robots_policy=policy,
    )

    assert page_transport_calls == []
    assert robots_fetches == ["https://93.184.216.34/robots.txt"]
    assert first.network_status == "robots_denied"
    assert first.content_invalid_reasons == ("robots_denied",)
    assert first.network_telemetry["robots_status"] == "denied"
    assert first.network_telemetry["robots_cache_hit"] is False
    assert second.network_telemetry["robots_cache_hit"] is True


def test_robots_allow_records_policy_telemetry():
    policy = web.RobotsPolicy(fetcher=lambda _url, _timeout: "User-agent: *\nAllow: /\n")
    response = FakeResponse(
        body=b"<html><body>A sufficiently detailed allowed public article for evidence.</body></html>",
        final_url="https://93.184.216.34/article",
    )

    result = web.fetch_page_result(
        "https://93.184.216.34/article",
        opener=FakeOpener(response),
        rendered_fetcher=lambda *args, **kwargs: None,
        robots_policy=policy,
    )

    assert result.network_status == "ok"
    assert result.network_telemetry["robots_status"] == "allowed"
    assert result.network_telemetry["robots_cache_hit"] is False


def test_http_rate_limit_has_distinct_status_and_bounded_retry_telemetry():
    policy = web.RobotsPolicy(fetcher=lambda _url, _timeout: "User-agent: *\nAllow: /\n")
    error = HTTPError(
        "https://93.184.216.34/article",
        429,
        "quota detail must not be recorded",
        {"Retry-After": "3"},
        FakeResponse(
            body=b"Rate limited",
            final_url="https://93.184.216.34/article",
            status=429,
        ),
    )

    class RaisingOpener:
        def open(self, request, timeout):
            raise error

    result = web.fetch_page_result(
        "https://93.184.216.34/article",
        opener=RaisingOpener(),
        robots_policy=policy,
    )

    assert result.network_status == "rate_limit"
    assert result.network_telemetry["retry_after_seconds"] == 3
    assert "quota detail" not in str(result.network_telemetry)
