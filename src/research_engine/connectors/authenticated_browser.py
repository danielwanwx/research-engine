"""Optional, user-consented Playwright recovery connector."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
from threading import Event, Thread
import time
from typing import Any
from urllib.parse import urljoin, urlsplit

from research_engine.browser_auth import (
    CapturePolicy,
    ConsentStore,
    DEFAULT_BROWSER_AUTH_ROOT,
    browser_profile_key,
    create_auth_challenge,
    normalize_origin,
    public_url,
)
from research_engine.browser_recipes import SiteRecipe, get_recipe
from research_engine.models import CollectionRequest, CollectionResult, utc_now
from research_engine.security import (
    sanitize_for_artifact,
    sensitive_paths,
    sensitive_value_paths,
)


LOGIN_TIMEOUT_SECONDS = 300
MAX_LOGIN_ATTEMPTS = 3
LOGIN_BROWSER_ENV = "RESEARCH_ENGINE_LOGIN_BROWSER"
HUMAN_LOGIN_STATUSES = {
    "consent_denied",
    "consent_timeout",
    "human_action_required",
    "login_browser_failed",
    "login_browser_timeout",
    "login_browser_unavailable",
    "login_cancelled",
    "login_incomplete",
    "login_timeout",
    "profile_lock_timeout",
}


@dataclass(frozen=True)
class BrowserFlowRequest:
    recipe: SiteRecipe
    target_url: str
    topic: str
    source: dict[str, Any]
    policy: CapturePolicy
    consent_required: bool
    profile_dir: Path
    login_timeout_seconds: int = LOGIN_TIMEOUT_SECONDS
    login_handoff: Callable[[Path, str, int], str] | None = None


@dataclass(frozen=True)
class BrowserFlowResult:
    status: str
    rows: list[dict[str, Any]]
    warnings: tuple[str, ...] = ()
    consent_granted: bool = False
    denied_requests: tuple[str, ...] = ()
    login_attempts: int = 0


BrowserFlow = Callable[[BrowserFlowRequest], BrowserFlowResult]


class AuthenticatedBrowserConnector:
    connector_id = "authenticated_browser"

    def __init__(
        self,
        *,
        consent_store: ConsentStore | None = None,
        browser_flow: BrowserFlow | None = None,
        login_handoff: Callable[[Path, str, int], str] | None = None,
        interactive: bool | Callable[[], bool] | None = None,
        auth_root: Path | None = None,
    ) -> None:
        root = Path(auth_root or DEFAULT_BROWSER_AUTH_ROOT).expanduser()
        self.consent_store = consent_store or ConsentStore(root)
        self.browser_flow = browser_flow or run_playwright_flow
        self.login_handoff = login_handoff
        self.interactive = interactive
        self.auth_root = root

    def collect(self, request: CollectionRequest) -> CollectionResult:
        recipe_id = str(request.source.get("recipe_id") or "")
        recipe = get_recipe(recipe_id)
        if not recipe:
            return self._empty(request, "recipe_missing", f"unknown browser recipe: {recipe_id}")

        target_url = str(request.source.get("target_url") or recipe.search_url(request.topic))
        if recipe.recipe_id == "generic" and target_url:
            try:
                recipe = replace(
                    recipe,
                    origins=(normalize_origin(target_url),),
                    display_name=urlsplit(target_url).hostname or recipe.display_name,
                )
            except ValueError:
                pass
        if not target_url or not recipe.accepts_url(target_url):
            return self._empty(
                request,
                "recipe_drift",
                f"target URL does not match recipe origin: {recipe.recipe_id}",
            )

        origin = normalize_origin(target_url)
        remembered = self.consent_store.has_consent(
            recipe_id=recipe.recipe_id,
            recipe_version=recipe.version,
            origin=origin,
        )
        challenge = create_auth_challenge(
            recipe_id=recipe.recipe_id,
            recipe_version=recipe.version,
            url=target_url,
            reason=str(request.source.get("challenge_reason") or "login_wall"),
            consent_required=not remembered,
        )
        if not self._is_interactive():
            payload = challenge.as_dict()
            payload["status"] = "human_action_required"
            self._annotate_gate_policy(
                request,
                payload,
                status="human_action_required",
                allow_advisory=True,
            )
            warning = "authenticated browser recovery requires an interactive session"
            if not payload["blocking"]:
                warning = (
                    f"{recipe.platform}_coverage_missing: authenticated source requires "
                    "an interactive login session"
                )
            return CollectionResult(
                source_id=request.source_id,
                connector=self.connector_id,
                rows=[],
                warnings=[warning],
                metadata={
                    "status": "human_action_required",
                    "auth_challenges": [payload],
                    "recipe_id": recipe.recipe_id,
                },
            )

        policy = CapturePolicy.for_request(
            origins=(origin,),
            max_results=request.max_results,
            depth=request.depth,
            read_only_post_operations=recipe.read_only_post_operations,
        )
        profile_dir = self.auth_root / "profiles" / browser_profile_key(
            recipe.recipe_id,
            origin=origin,
        )
        try:
            result = self.browser_flow(
                BrowserFlowRequest(
                    recipe=recipe,
                    target_url=target_url,
                    topic=request.topic,
                    source=dict(request.source),
                    policy=policy,
                    consent_required=not remembered,
                    profile_dir=profile_dir,
                    login_handoff=self.login_handoff,
                )
            )
        except ImportError:
            return self._challenge_result(request, recipe, challenge, "browser_unavailable")
        except Exception as exc:
            return self._challenge_result(
                request,
                recipe,
                challenge,
                "browser_failed",
                warning=f"browser recovery failed: {type(exc).__name__}: {exc}",
            )

        if result.consent_granted and not remembered:
            self.consent_store.grant(
                recipe_id=recipe.recipe_id,
                recipe_version=recipe.version,
                origin=origin,
            )

        original_rows = [dict(row) for row in result.rows]
        for row in original_rows:
            if row.get("url"):
                row["url"] = public_url(str(row["url"]))
        if sensitive_paths(original_rows) or sensitive_value_paths(original_rows):
            return self._challenge_result(
                request,
                recipe,
                challenge,
                "sensitive_output_blocked",
                warning="browser output contained sensitive state and was discarded",
            )
        rows = [
            self._normalize_row(request, recipe, target_url, row)
            for row in sanitize_for_artifact(original_rows)
        ]
        challenge_payload = challenge.as_dict()
        challenge_payload["status"] = (
            "completed" if result.status == "ready" else result.status
        )
        challenge_payload["human_action_required"] = result.status in HUMAN_LOGIN_STATUSES
        challenge_payload["login_attempts"] = result.login_attempts
        self._annotate_gate_policy(
            request,
            challenge_payload,
            status=result.status,
            allow_advisory=False,
        )
        result_warnings = list(result.warnings)
        if result.status != "ready" and not result_warnings:
            result_warnings.append(result.status.replace("_", " "))
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=rows,
            warnings=result_warnings,
            metadata={
                "status": result.status,
                "recipe_id": recipe.recipe_id,
                "recipe_version": recipe.version,
                "consent_remembered": remembered,
                "denied_request_count": len(result.denied_requests),
                "login_attempts": result.login_attempts,
                "auth_challenges": [challenge_payload],
            },
        )

    def _is_interactive(self) -> bool:
        if callable(self.interactive):
            return bool(self.interactive())
        if self.interactive is not None:
            return bool(self.interactive)
        if not sys.stdin.isatty():
            return False
        return sys.platform == "darwin" or bool(os.environ.get("DISPLAY"))

    def _normalize_row(
        self,
        request: CollectionRequest,
        recipe: SiteRecipe,
        target_url: str,
        row: dict[str, Any],
    ) -> dict[str, Any]:
        source = request.source
        text = str(row.get("text") or "").strip()[:4000]
        return {
            "source_id": request.source_id,
            "connector": self.connector_id,
            "platform": recipe.platform,
            "title": str(row.get("title") or recipe.display_name).strip()[:500],
            "url": str(row.get("url") or public_url(target_url)),
            "publisher": str(row.get("publisher") or row.get("author") or recipe.display_name),
            "author": str(row.get("author") or ""),
            "published_at": str(row.get("published_at") or ""),
            "captured_at": utc_now(),
            "text": text,
            "source_confidence": str(row.get("source_confidence") or "medium"),
            "content_valid": bool(text),
            "content_invalid": not bool(text),
            "content_invalid_reasons": [] if text else ["empty_content"],
            "access_mode": "user_consented_browser",
            "is_final_page": bool(text),
            **{
                key: source[key]
                for key in ("query_id", "facet_id", "pass", "query")
                if key in source
            },
        }

    def _empty(
        self,
        request: CollectionRequest,
        status: str,
        warning: str,
    ) -> CollectionResult:
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=[],
            warnings=[warning],
            metadata={"status": status, "auth_challenges": []},
        )

    def _challenge_result(
        self,
        request: CollectionRequest,
        recipe: SiteRecipe,
        challenge: Any,
        status: str,
        *,
        warning: str | None = None,
    ) -> CollectionResult:
        payload = challenge.as_dict()
        payload["status"] = status
        payload["human_action_required"] = status in HUMAN_LOGIN_STATUSES
        self._annotate_gate_policy(
            request,
            payload,
            status=status,
            allow_advisory=False,
        )
        resolved_warning = warning or status.replace("_", " ")
        return CollectionResult(
            source_id=request.source_id,
            connector=self.connector_id,
            rows=[],
            warnings=[resolved_warning],
            metadata={
                "status": status,
                "recipe_id": recipe.recipe_id,
                "auth_challenges": [payload],
            },
        )

    @staticmethod
    def _annotate_gate_policy(
        request: CollectionRequest,
        payload: dict[str, Any],
        *,
        status: str,
        allow_advisory: bool,
    ) -> None:
        policy = str(request.source.get("auth_gate_policy") or "blocking")
        advisory = policy == "advisory" and allow_advisory
        payload["auth_gate_policy"] = policy
        payload["blocking"] = not advisory
        payload["coverage_missing"] = policy == "advisory" and status != "ready"


def run_playwright_flow(flow: BrowserFlowRequest) -> BrowserFlowResult:
    """Run the visible Playwright flow; imported lazily to keep it optional."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ImportError("install research-engine[browser] and Playwright Chromium") from exc

    flow.profile_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(flow.profile_dir, 0o700)
    with sync_playwright() as playwright:  # pragma: no cover - exercised by live smoke
        return _run_playwright_flow(playwright, flow)


def _run_playwright_flow(playwright: Any, flow: BrowserFlowRequest) -> BrowserFlowResult:
    denied_requests: list[str] = []
    login_attempts = 0
    context = _launch_capture_context(playwright, flow.profile_dir)
    try:
        page = context.pages[0] if context.pages else context.new_page()
        if flow.consent_required:
            consent = _wait_for_consent(page, flow)
            if consent == "deny":
                return BrowserFlowResult("consent_denied", [], consent_granted=False)
            if consent != "allow":
                return BrowserFlowResult("consent_timeout", [], consent_granted=False)

        page.goto(flow.target_url, wait_until="domcontentloaded", timeout=30_000)
        login_deadline = time.monotonic() + flow.login_timeout_seconds
        while _any_visible(page, flow.recipe.login_markers):
            if login_attempts >= MAX_LOGIN_ATTEMPTS:
                return BrowserFlowResult(
                    "login_incomplete",
                    [],
                    consent_granted=True,
                    login_attempts=login_attempts,
                )
            remaining = math.ceil(login_deadline - time.monotonic())
            if remaining <= 0:
                return BrowserFlowResult(
                    "login_timeout",
                    [],
                    consent_granted=True,
                    login_attempts=login_attempts,
                )
            context.close()
            context = None
            notice = (
                "Sign-in was not detected after the previous confirmation. "
                "Please finish the site login before continuing again."
                if login_attempts
                else ""
            )
            login_attempts += 1
            handoff_status = (
                flow.login_handoff(
                    flow.profile_dir,
                    flow.target_url,
                    remaining,
                )
                if flow.login_handoff
                else run_native_login_handoff(
                    flow.profile_dir,
                    flow.target_url,
                    remaining,
                    notice,
                )
            )
            if handoff_status != "ready":
                return BrowserFlowResult(
                    handoff_status,
                    [],
                    consent_granted=True,
                    login_attempts=login_attempts,
                )
            context = _launch_capture_context(playwright, flow.profile_dir)
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(flow.target_url, wait_until="domcontentloaded", timeout=30_000)

        context.route(
            "**/*",
            lambda route, request: _guard_request(
                route,
                request,
                flow.policy,
                denied_requests,
            ),
        )
        rows = _capture_rows(page, flow)
        status = "ready" if rows else "recipe_drift"
        warnings = () if rows else ("browser recipe matched no visible result rows",)
        return BrowserFlowResult(
            status,
            rows,
            warnings=warnings,
            consent_granted=True,
            denied_requests=tuple(denied_requests),
            login_attempts=login_attempts,
        )
    finally:
        if context is not None:
            context.close()


def _launch_capture_context(playwright: Any, profile_dir: Path) -> Any:
    return playwright.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        headless=False,
        accept_downloads=False,
        service_workers="block",
    )


def resolve_login_browser(
    *,
    environ: dict[str, str] | None = None,
    platform_name: str | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> str:
    env = os.environ if environ is None else environ
    platform_id = platform_name or sys.platform
    override = str(env.get(LOGIN_BROWSER_ENV) or "").strip()
    if override:
        return override if _eligible_login_browser(Path(override).expanduser()) else ""

    candidates: list[Path] = []
    if platform_id == "darwin":
        candidates.append(
            Path(
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            )
        )
    elif platform_id == "win32":
        for root_name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            if root := env.get(root_name):
                candidates.append(Path(root) / "Google/Chrome/Application/chrome.exe")
    else:
        for command in (
            "google-chrome",
            "google-chrome-stable",
            "chromium",
            "chromium-browser",
        ):
            if path := which(command):
                candidates.append(Path(path))
    return str(next((path for path in candidates if _eligible_login_browser(path)), ""))


def _eligible_login_browser(path: Path) -> bool:
    lowered = str(path.resolve(strict=False)).casefold()
    return (
        path.is_file()
        and os.access(path, os.X_OK)
        and "chrome for testing" not in lowered
        and "ms-playwright" not in lowered
    )


def run_native_login_handoff(
    profile_dir: Path,
    target_url: str,
    timeout_seconds: int,
    notice: str = "",
    *,
    executable: str = "",
    popen_fn: Callable[..., Any] = subprocess.Popen,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
    profile_unlock_timeout_seconds: float = 10.0,
    confirmation_factory: Callable[[str, str], Any] | None = None,
) -> str:
    browser = executable or resolve_login_browser()
    if not browser:
        return "login_browser_unavailable"
    confirmation = (confirmation_factory or _LoginConfirmation)(target_url, notice)
    confirmation.start()
    command = [
        browser,
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--disable-background-mode",
        "--new-window",
        confirmation.url,
        public_url(target_url),
    ]
    print(
        "Complete login, then return to the Research Engine tab and click Continue.",
        file=sys.stderr,
        flush=True,
    )
    try:
        process = popen_fn(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )
    except OSError:
        confirmation.close()
        return "login_browser_failed"
    try:
        deadline = monotonic_fn() + max(1, int(timeout_seconds))
        while True:
            if confirmation.completed.is_set():
                status = confirmation.status or "login_browser_failed"
                _stop_login_browser(process)
                break
            remaining = deadline - monotonic_fn()
            if remaining <= 0:
                _stop_login_browser(process)
                status = "login_browser_timeout"
                break
            try:
                return_code = process.wait(timeout=min(0.25, remaining))
            except subprocess.TimeoutExpired:
                continue
            status = "ready" if return_code == 0 else "login_browser_failed"
            break
    finally:
        confirmation.close()
    if status != "ready":
        return status

    deadline = monotonic_fn() + max(0.0, profile_unlock_timeout_seconds)
    while _profile_is_locked(profile_dir):
        if monotonic_fn() >= deadline:
            return "profile_lock_timeout"
        sleep_fn(0.1)
    return "ready"


def _stop_login_browser(process: Any) -> None:
    try:
        process.terminate()
    except OSError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


class _LoginConfirmation:
    def __init__(self, target_url: str, notice: str = "") -> None:
        self.completed = Event()
        self.status = ""
        self._token = secrets.token_urlsafe(18)
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path != f"/{outer._token}":
                    self.send_error(404)
                    return
                self._send_html(_login_confirmation_html(target_url, outer._token, notice))

            def do_POST(self) -> None:  # noqa: N802
                statuses = {
                    f"/{outer._token}/done": "ready",
                    f"/{outer._token}/cancel": "login_cancelled",
                }
                status = statuses.get(self.path)
                if not status:
                    self.send_error(404)
                    return
                body = (
                    "<h1>Login confirmed</h1><p>Research Engine is resuming "
                    "read-only capture. This dedicated window may close.</p>"
                    if status == "ready"
                    else "<h1>Cancelled</h1><p>No authenticated capture will run.</p>"
                )
                self._send_html(body)
                outer.status = status
                outer.completed.set()

            def _send_html(self, body: str) -> None:
                payload = (
                    "<!doctype html><meta charset=utf-8><title>Research Engine</title>"
                    f"<body>{body}</body>"
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'none'; style-src 'unsafe-inline'",
                )
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format: str, *args: Any) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = self._server.server_address[1]
        self.url = f"http://127.0.0.1:{port}/{self._token}"
        self._thread = Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=1)


def _login_confirmation_html(target_url: str, token: str, notice: str = "") -> str:
    safe_target = escape(public_url(target_url), quote=True)
    safe_notice = escape(notice)
    notice_html = f'<p class="notice">{safe_notice}</p>' if safe_notice else ""
    return f"""
<style>
body{{font:16px system-ui;max-width:680px;margin:12vh auto;padding:0 24px;color:#172033}}
a,button{{font:inherit;padding:10px 16px;margin:10px 8px 0 0}}button{{cursor:pointer}}
.continue{{background:#1565c0;color:white;border:0;border-radius:5px}}
.notice{{background:#fff4d6;border:1px solid #e0b84f;border-radius:6px;padding:12px}}
</style>
<h1>Finish sign-in, then continue</h1>
{notice_html}
<p>Sign in on the other tab. Return here only after the site shows you are logged in.</p>
<p>When you continue, this Chrome window closes briefly so Research Engine can verify the
session. If sign-in is still incomplete, the login window will reopen automatically.</p>
<p><a href="{safe_target}" target="_blank" rel="noopener">Open the site login again</a></p>
<form method="post" action="/{token}/done">
<button class="continue" type="submit">Close window and verify sign-in</button>
</form>
<form method="post" action="/{token}/cancel">
<button type="submit">Cancel</button>
</form>
"""


def _profile_is_locked(profile_dir: Path) -> bool:
    return any(
        os.path.lexists(profile_dir / name)
        for name in ("SingletonCookie", "SingletonLock", "SingletonSocket")
    )


def _consent_html(flow: BrowserFlowRequest) -> str:
    site = escape(flow.recipe.display_name)
    origin = escape(normalize_origin(flow.target_url))
    return f"""<!doctype html><meta charset="utf-8"><title>Research access consent</title>
<style>body{{font:16px system-ui;max-width:680px;margin:12vh auto;padding:32px;color:#172033}}
button{{font:inherit;padding:10px 18px;margin:12px 8px 0 0}} .allow{{background:#1565c0;color:white}}</style>
<h1>Allow read-only research on {site}?</h1>
<p>Research Engine will open <strong>{origin}</strong> in this dedicated browser profile.
If sign-in is required, a normal Chrome window opens for you to handle SSO, MFA, or
CAPTCHA. Return to its Research Engine tab and click Continue when finished; bounded
read-only collection then resumes.</p>
<p>No cookies, passwords, screenshots, traces, or browser storage are copied into reports.</p>
<button class="allow" id="allow">Allow and remember</button>
<button id="deny">Cancel</button>
<script>allow.onclick=()=>document.body.dataset.decision='allow';
deny.onclick=()=>document.body.dataset.decision='deny';</script>"""


def _wait_for_consent(page: Any, flow: BrowserFlowRequest) -> str:
    page.set_content(_consent_html(flow), wait_until="domcontentloaded")
    deadline = time.monotonic() + flow.login_timeout_seconds
    while time.monotonic() < deadline:
        decision = page.get_attribute("body", "data-decision") or ""
        if decision in {"allow", "deny"}:
            return decision
        page.wait_for_timeout(250)
    return "timeout"


def _any_visible(page: Any, selectors: tuple[str, ...]) -> bool:
    for selector in selectors:
        try:
            if page.locator(selector).first.is_visible(timeout=250):
                return True
        except Exception:
            continue
    return False


def _guard_request(
    route: Any,
    request: Any,
    policy: CapturePolicy,
    denied_requests: list[str],
) -> None:
    method = str(request.method).upper()
    if method in {"GET", "HEAD", "OPTIONS"} and not request.is_navigation_request():
        route.continue_()
        return
    operation = _operation_name(request)
    allowed, reason = policy.check_request(method=method, url=request.url, operation=operation)
    if allowed:
        route.continue_()
        return
    denied_requests.append(reason)
    route.abort("blockedbyclient")


def _operation_name(request: Any) -> str:
    try:
        payload = json.loads(request.post_data or "{}")
    except (TypeError, json.JSONDecodeError):
        payload = {}
    if isinstance(payload, dict) and payload.get("operationName"):
        return str(payload["operationName"])
    url_path = urlsplit(str(request.url)).path.rstrip("/")
    return url_path.rsplit("/", 1)[-1]


def _capture_rows(page: Any, flow: BrowserFlowRequest) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    pages = 0
    scrolls = 0
    while pages < flow.policy.max_pages and len(rows) < flow.policy.max_results:
        pages += 1
        selector = _first_populated_selector(page, flow.recipe.item_selectors)
        if selector:
            items = page.locator(selector)
            for index in range(min(items.count(), flow.policy.max_results)):
                item = items.nth(index)
                text = _first_text(item, flow.recipe.text_selectors) or _safe_inner_text(item)
                title = _first_text(item, flow.recipe.title_selectors)
                author = _first_text(item, flow.recipe.author_selectors)
                published = _first_text(item, flow.recipe.time_selectors)
                href = _first_attribute(item, flow.recipe.link_selectors, "href")
                url = urljoin(flow.target_url, href) if href else flow.target_url
                key = (url, text)
                if not text or key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "title": title or text[:160],
                        "text": text,
                        "author": author,
                        "published_at": published,
                        "url": url,
                    }
                )
                if len(rows) >= flow.policy.max_results:
                    break
        if len(rows) >= flow.policy.max_results:
            break
        if scrolls < flow.policy.max_scrolls:
            allowed, _ = flow.policy.check_action("scroll")
            if allowed:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(750)
                scrolls += 1
                continue
        next_selector = _first_visible_selector(page, flow.recipe.next_page_selectors)
        allowed, _ = flow.policy.check_action("next_page")
        if not next_selector or not allowed:
            break
        page.locator(next_selector).first.click(timeout=2_000)
        page.wait_for_load_state("domcontentloaded", timeout=10_000)
    return rows


def _first_populated_selector(page: Any, selectors: tuple[str, ...]) -> str:
    for selector in selectors:
        try:
            if page.locator(selector).count():
                return selector
        except Exception:
            continue
    return ""


def _first_visible_selector(page: Any, selectors: tuple[str, ...]) -> str:
    for selector in selectors:
        try:
            if page.locator(selector).first.is_visible(timeout=250):
                return selector
        except Exception:
            continue
    return ""


def _first_text(item: Any, selectors: tuple[str, ...]) -> str:
    for selector in selectors:
        try:
            value = item.locator(selector).first.text_content(timeout=500)
        except Exception:
            continue
        text = " ".join(str(value or "").split())
        if text:
            return text[:4000]
    return ""


def _first_attribute(item: Any, selectors: tuple[str, ...], name: str) -> str:
    for selector in selectors:
        try:
            value = item.locator(selector).first.get_attribute(name, timeout=500)
        except Exception:
            continue
        if value:
            return str(value)
    return ""


def _safe_inner_text(item: Any) -> str:
    try:
        return " ".join(str(item.inner_text(timeout=500) or "").split())[:4000]
    except Exception:
        return ""
