import subprocess
from threading import Event

from research_engine.browser_auth import CapturePolicy
from research_engine.browser_auth import ConsentStore
from research_engine.browser_recipes import get_recipe
import research_engine.connectors.authenticated_browser as browser_module
from research_engine.connectors.authenticated_browser import (
    AuthenticatedBrowserConnector,
    BrowserFlowRequest,
    BrowserFlowResult,
    resolve_login_browser,
    run_native_login_handoff,
)
from research_engine.models import CollectionRequest


class FakeConfirmation:
    def __init__(self, target_url, notice="", status=""):
        self.completed = Event()
        self.status = status
        self.notice = notice
        self.url = "http://127.0.0.1:12345/test-token"
        if status:
            self.completed.set()

    def start(self):
        pass

    def close(self):
        pass


def request():
    return CollectionRequest(
        source={
            "source_id": "browser-linkedin",
            "recipe_id": "linkedin",
            "target_url": "https://www.linkedin.com/search/results/content/?keywords=agents",
            "query_id": "q1",
            "facet_id": "community",
            "pass": 2,
        },
        topic="agents",
        run_date="2026-07-17",
        depth="quick",
        max_results=3,
    )


def test_noninteractive_path_records_human_gate_without_launching(tmp_path):
    launched = []
    connector = AuthenticatedBrowserConnector(
        consent_store=ConsentStore(tmp_path),
        browser_flow=lambda flow: launched.append(flow),
        interactive=False,
        auth_root=tmp_path,
    )

    result = connector.collect(request())

    assert result.metadata["status"] == "human_action_required"
    assert result.metadata["auth_challenges"][0]["consent_required"] is True
    assert launched == []


def test_noninteractive_advisory_source_records_coverage_gap_without_blocking(tmp_path):
    advisory_request = request()
    advisory_request.source["auth_gate_policy"] = "advisory"
    connector = AuthenticatedBrowserConnector(
        consent_store=ConsentStore(tmp_path),
        interactive=False,
        auth_root=tmp_path,
    )

    result = connector.collect(advisory_request)

    challenge = result.metadata["auth_challenges"][0]
    assert challenge["blocking"] is False
    assert challenge["coverage_missing"] is True
    assert "linkedin_coverage_missing" in result.warnings[0]


def test_granted_flow_normalizes_rows_and_remembers_consent(tmp_path):
    observed = []

    def flow(payload):
        observed.append(payload)
        return BrowserFlowResult(
            "ready",
            [{"title": "Agent post", "text": "Useful evidence", "url": payload.target_url}],
            consent_granted=True,
        )

    store = ConsentStore(tmp_path)
    connector = AuthenticatedBrowserConnector(
        consent_store=store,
        browser_flow=flow,
        interactive=True,
        auth_root=tmp_path,
    )

    first = connector.collect(request())
    second = connector.collect(request())

    assert first.metadata["status"] == "ready"
    assert first.rows[0]["access_mode"] == "user_consented_browser"
    assert first.rows[0]["query_id"] == "q1"
    assert first.rows[0]["facet_id"] == "community"
    assert first.rows[0]["pass"] == 2
    assert first.metadata["auth_challenges"][0]["status"] == "completed"
    assert observed[0].consent_required is True
    assert observed[1].consent_required is False
    assert second.metadata["consent_remembered"] is True


def test_denied_consent_produces_no_rows_or_grant(tmp_path):
    store = ConsentStore(tmp_path)
    connector = AuthenticatedBrowserConnector(
        consent_store=store,
        browser_flow=lambda flow: BrowserFlowResult("consent_denied", []),
        interactive=True,
        auth_root=tmp_path,
    )

    result = connector.collect(request())

    assert result.rows == []
    assert result.metadata["status"] == "consent_denied"
    assert result.warnings == ["consent denied"]
    assert store.list_grants() == []


def test_sensitive_browser_output_is_discarded(tmp_path):
    connector = AuthenticatedBrowserConnector(
        consent_store=ConsentStore(tmp_path),
        browser_flow=lambda flow: BrowserFlowResult(
            "ready",
            [{"text": "evidence", "cookie": "secret", "url": flow.target_url}],
            consent_granted=True,
        ),
        interactive=True,
        auth_root=tmp_path,
    )

    result = connector.collect(request())

    assert result.rows == []
    assert result.metadata["status"] == "sensitive_output_blocked"


def test_recipe_origin_mismatch_stops_before_browser(tmp_path):
    source = dict(request().source)
    source["target_url"] = "https://evil.example/search"
    bad_request = CollectionRequest(
        source=source,
        topic="agents",
        run_date="2026-07-17",
        depth="quick",
        max_results=3,
    )
    connector = AuthenticatedBrowserConnector(interactive=True, auth_root=tmp_path)

    result = connector.collect(bad_request)

    assert result.metadata["status"] == "recipe_drift"


def test_generic_recipe_uses_an_origin_isolated_profile(tmp_path):
    observed = []
    generic_request = CollectionRequest(
        source={
            "source_id": "browser-generic",
            "recipe_id": "generic",
            "target_url": "https://community.example/private/topic",
        },
        topic="community topic",
        run_date="2026-07-17",
        depth="quick",
        max_results=2,
    )
    connector = AuthenticatedBrowserConnector(
        consent_store=ConsentStore(tmp_path),
        browser_flow=lambda flow: observed.append(flow)
        or BrowserFlowResult("ready", [{"text": "visible article"}], consent_granted=True),
        interactive=True,
        auth_root=tmp_path,
    )

    result = connector.collect(generic_request)

    assert result.metadata["status"] == "ready"
    assert observed[0].recipe.origins == ("https://community.example",)
    assert observed[0].profile_dir.name.startswith("generic-")


def test_login_browser_resolution_honors_valid_override_and_rejects_testing(tmp_path):
    chrome = tmp_path / "Google Chrome"
    chrome.write_text("fixture")
    chrome.chmod(0o700)
    testing = tmp_path / "Chrome for Testing"
    testing.write_text("fixture")
    testing.chmod(0o700)

    assert resolve_login_browser(
        environ={"RESEARCH_ENGINE_LOGIN_BROWSER": str(chrome)},
        platform_name="darwin",
    ) == str(chrome)
    assert not resolve_login_browser(
        environ={"RESEARCH_ENGINE_LOGIN_BROWSER": str(testing)},
        platform_name="darwin",
    )


def test_native_login_handoff_uses_safe_argv_and_waits_for_close(tmp_path):
    observed = {}

    class Process:
        def wait(self, *, timeout):
            observed["timeout"] = timeout
            return 0

    def popen(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        return Process()

    def confirmation(target, notice):
        observed["notice"] = notice
        return FakeConfirmation(target, notice)

    result = run_native_login_handoff(
        tmp_path / "profile",
        "https://www.linkedin.com/search?q=private-query",
        300,
        "Sign-in was not detected",
        executable="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        popen_fn=popen,
        confirmation_factory=confirmation,
    )

    assert result == "ready"
    assert observed["timeout"] == 0.25
    assert observed["kwargs"]["shell"] is False
    assert observed["notice"] == "Sign-in was not detected"
    command = observed["command"]
    assert command[-1] == "https://www.linkedin.com/search"
    assert any(part.startswith("http://127.0.0.1:") for part in command)
    assert not any("remote-debugging" in part or "automation" in part for part in command)
    assert any(part.startswith("--user-data-dir=") for part in command)


def test_native_login_handoff_terminates_its_process_on_timeout(tmp_path):
    class Process:
        terminated = False

        def wait(self, *, timeout):
            if self.terminated:
                return 0
            raise subprocess.TimeoutExpired("chrome", timeout)

        def terminate(self):
            self.terminated = True

    process = Process()
    result = run_native_login_handoff(
        tmp_path / "profile",
        "https://www.linkedin.com/login",
        1,
        executable="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        popen_fn=lambda *args, **kwargs: process,
        monotonic_fn=iter((0.0, 2.0)).__next__,
        confirmation_factory=FakeConfirmation,
    )

    assert result == "login_browser_timeout"
    assert process.terminated


def test_native_login_handoff_accepts_browser_confirmation(tmp_path):
    stopped = Event()

    class Process:
        def wait(self, *, timeout):
            if stopped.wait(timeout):
                return -15
            raise subprocess.TimeoutExpired("chrome", timeout)

        def terminate(self):
            stopped.set()

    assert run_native_login_handoff(
        tmp_path / "profile",
        "https://www.linkedin.com/login",
        2,
        executable="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        popen_fn=lambda *args, **kwargs: Process(),
        confirmation_factory=lambda target, notice: FakeConfirmation(target, notice, "ready"),
    ) == "ready"
    assert stopped.is_set()


def test_native_login_handoff_stops_when_profile_lock_remains(tmp_path):
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "SingletonLock").write_text("locked")

    class Process:
        def wait(self, *, timeout):
            return 0

    assert run_native_login_handoff(
        profile,
        "https://www.linkedin.com/login",
        1,
        executable="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        popen_fn=lambda *args, **kwargs: Process(),
        monotonic_fn=lambda: 0.0,
        profile_unlock_timeout_seconds=0,
        confirmation_factory=FakeConfirmation,
    ) == "profile_lock_timeout"


def test_playwright_context_closes_before_native_login_and_reopens(monkeypatch, tmp_path):
    events = []

    class Page:
        def __init__(self, number):
            self.number = number

        def goto(self, *args, **kwargs):
            events.append(f"goto-{self.number}")

    class Context:
        def __init__(self, number):
            self.number = number
            self.pages = [Page(number)]

        def close(self):
            events.append(f"close-{self.number}")

        def route(self, *args, **kwargs):
            events.append(f"route-{self.number}")

    class Chromium:
        def __init__(self):
            self.count = 0

        def launch_persistent_context(self, **kwargs):
            self.count += 1
            events.append(f"launch-{self.count}")
            return Context(self.count)

    class Playwright:
        chromium = Chromium()

    visible = iter((True, False))
    monkeypatch.setattr(browser_module, "_any_visible", lambda page, selectors: next(visible))
    monkeypatch.setattr(
        browser_module,
        "_capture_rows",
        lambda page, flow: [{"text": "captured after login"}],
    )
    recipe = get_recipe("linkedin")
    assert recipe is not None
    flow = BrowserFlowRequest(
        recipe=recipe,
        target_url=recipe.search_url("agents"),
        topic="agents",
        source={},
        policy=CapturePolicy.for_request(
            origins=("https://www.linkedin.com",), max_results=1, depth="quick"
        ),
        consent_required=False,
        profile_dir=tmp_path / "profile",
        login_handoff=lambda profile, url, timeout: events.append("handoff") or "ready",
    )

    result = browser_module._run_playwright_flow(Playwright(), flow)

    assert result.status == "ready"
    assert result.login_attempts == 1
    assert events.index("close-1") < events.index("handoff") < events.index("launch-2")
    assert "route-2" in events


def test_incomplete_login_reopens_native_chrome_and_retries(monkeypatch, tmp_path):
    events = []

    class Page:
        def __init__(self, number):
            self.number = number

        def goto(self, *args, **kwargs):
            events.append(f"goto-{self.number}")

    class Context:
        def __init__(self, number):
            self.number = number
            self.pages = [Page(number)]

        def close(self):
            events.append(f"close-{self.number}")

        def route(self, *args, **kwargs):
            events.append(f"route-{self.number}")

    class Chromium:
        def __init__(self):
            self.count = 0

        def launch_persistent_context(self, **kwargs):
            self.count += 1
            events.append(f"launch-{self.count}")
            return Context(self.count)

    class Playwright:
        chromium = Chromium()

    visible = iter((True, True, False))
    handoffs = []

    def handoff(profile, url, timeout):
        handoffs.append(timeout)
        events.append("handoff")
        return "ready"

    monkeypatch.setattr(browser_module, "_any_visible", lambda page, selectors: next(visible))
    monkeypatch.setattr(
        browser_module,
        "_capture_rows",
        lambda page, flow: [{"text": "captured after retry"}],
    )
    recipe = get_recipe("linkedin")
    assert recipe is not None
    flow = BrowserFlowRequest(
        recipe=recipe,
        target_url=recipe.search_url("agents"),
        topic="agents",
        source={},
        policy=CapturePolicy.for_request(
            origins=("https://www.linkedin.com",), max_results=1, depth="quick"
        ),
        consent_required=False,
        profile_dir=tmp_path / "profile",
        login_handoff=handoff,
    )

    result = browser_module._run_playwright_flow(Playwright(), flow)

    assert result.status == "ready"
    assert result.login_attempts == 2
    assert len(handoffs) == 2
    second_close = events.index("close-2")
    assert events[second_close : second_close + 3] == ["close-2", "handoff", "launch-3"]


def test_login_retry_stops_after_three_confirmations(monkeypatch, tmp_path):
    class Page:
        def goto(self, *args, **kwargs):
            pass

    class Context:
        pages = [Page()]

        def close(self):
            pass

        def route(self, *args, **kwargs):
            pass

    class Chromium:
        def launch_persistent_context(self, **kwargs):
            return Context()

    class Playwright:
        chromium = Chromium()

    monkeypatch.setattr(browser_module, "_any_visible", lambda page, selectors: True)
    recipe = get_recipe("linkedin")
    assert recipe is not None
    flow = BrowserFlowRequest(
        recipe=recipe,
        target_url=recipe.search_url("agents"),
        topic="agents",
        source={},
        policy=CapturePolicy.for_request(
            origins=("https://www.linkedin.com",), max_results=1, depth="quick"
        ),
        consent_required=False,
        profile_dir=tmp_path / "profile",
        login_handoff=lambda profile, url, timeout: "ready",
    )

    result = browser_module._run_playwright_flow(Playwright(), flow)

    assert result.status == "login_incomplete"
    assert result.login_attempts == 3


def test_login_retries_share_one_timeout_budget(monkeypatch, tmp_path):
    class Page:
        def goto(self, *args, **kwargs):
            pass

    class Context:
        pages = [Page()]

        def close(self):
            pass

    monotonic = iter((0.0, 1.0, 6.0)).__next__
    handoff_timeouts = []
    monkeypatch.setattr(browser_module, "_launch_capture_context", lambda *args: Context())
    monkeypatch.setattr(browser_module, "_any_visible", lambda page, selectors: True)
    monkeypatch.setattr(browser_module.time, "monotonic", monotonic)
    recipe = get_recipe("linkedin")
    assert recipe is not None
    flow = BrowserFlowRequest(
        recipe=recipe,
        target_url=recipe.search_url("agents"),
        topic="agents",
        source={},
        policy=CapturePolicy.for_request(
            origins=("https://www.linkedin.com",), max_results=1, depth="quick"
        ),
        consent_required=False,
        profile_dir=tmp_path / "profile",
        login_timeout_seconds=5,
        login_handoff=lambda profile, url, timeout: handoff_timeouts.append(timeout) or "ready",
    )

    result = browser_module._run_playwright_flow(object(), flow)

    assert result.status == "login_timeout"
    assert result.login_attempts == 1
    assert handoff_timeouts == [4]


def test_login_handoff_failure_remains_a_human_gate(tmp_path):
    connector = AuthenticatedBrowserConnector(
        consent_store=ConsentStore(tmp_path),
        browser_flow=lambda flow: BrowserFlowResult(
            "login_browser_unavailable", [], consent_granted=True
        ),
        interactive=True,
        auth_root=tmp_path,
    )

    result = connector.collect(request())

    assert result.metadata["status"] == "login_browser_unavailable"
    assert result.metadata["auth_challenges"][0]["human_action_required"] is True


def test_interactive_advisory_login_failure_remains_a_blocking_human_gate(tmp_path):
    advisory_request = request()
    advisory_request.source["auth_gate_policy"] = "advisory"
    connector = AuthenticatedBrowserConnector(
        consent_store=ConsentStore(tmp_path),
        browser_flow=lambda flow: BrowserFlowResult(
            "login_incomplete", [], consent_granted=True, login_attempts=3
        ),
        interactive=True,
        auth_root=tmp_path,
    )

    result = connector.collect(advisory_request)

    challenge = result.metadata["auth_challenges"][0]
    assert challenge["blocking"] is True
    assert challenge["coverage_missing"] is True
    assert challenge["login_attempts"] == 3
