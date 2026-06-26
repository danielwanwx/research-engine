import subprocess

from research_engine.connectors.opencli import (
    OpenCliBridgeConnector,
    parse_structured_output,
    render_command_template,
)
from research_engine.models import CollectionRequest
from research_engine.runner import DEFAULT_CONNECTORS


def request(source_overrides=None, *, max_results=3):
    source = {
        "source_id": "opencli_seed",
        "connector": "opencli_bridge",
        "platform": "x",
        "query": "loop engineering",
        "command": 'opencli x search --query "{query}" --limit {max_results} --format json',
    }
    source.update(source_overrides or {})
    return CollectionRequest(
        source=source,
        topic="loop engineering",
        run_date="2026-06-26",
        depth="quick",
        max_results=max_results,
    )


def test_opencli_bridge_is_registered_by_default():
    assert DEFAULT_CONNECTORS["opencli_bridge"] is OpenCliBridgeConnector


def test_render_command_template_keeps_query_together():
    command = render_command_template(
        'opencli x search --query "{query}" --platform {platform} --limit {max_results}',
        platform="x",
        query="loop engineering",
        max_results=5,
    )

    assert command == [
        "opencli",
        "x",
        "search",
        "--query",
        "loop engineering",
        "--platform",
        "x",
        "--limit",
        "5",
    ]


def test_render_command_template_keeps_unquoted_query_as_one_argv_part():
    command = render_command_template(
        "opencli x search --query {query} --limit {max_results}",
        platform="x",
        query="loop engineering",
        max_results=5,
    )

    assert command == ["opencli", "x", "search", "--query", "loop engineering", "--limit", "5"]


def test_render_command_template_accepts_argv_list():
    command = render_command_template(
        ["opencli", "x", "search", "--query", "{query}", "--limit", "{max_results}"],
        platform="x",
        query="self learning agents",
        max_results=2,
    )

    assert command == ["opencli", "x", "search", "--query", "self learning agents", "--limit", "2"]


def test_opencli_bridge_requires_command_template():
    connector = OpenCliBridgeConnector(which=lambda command: "/usr/local/bin/opencli")
    result = connector.collect(request({"command": "", "command_templates": []}))

    assert result.rows == []
    assert "requires a command" in result.warnings[0]


def test_opencli_bridge_warns_when_command_missing():
    connector = OpenCliBridgeConnector(which=lambda command: None)
    result = connector.collect(request())

    assert result.rows == []
    assert "command not found" in result.warnings[0]
    assert result.metadata["opencli_installed"] is False


def test_opencli_bridge_parses_json_array_output():
    calls = []

    def fake_runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='[{"title":"Loop post","url":"https://x.com/example","text":"Harness layer"}]',
            stderr="",
        )

    connector = OpenCliBridgeConnector(
        runner=fake_runner,
        which=lambda command: "/usr/local/bin/opencli" if command == "opencli" else None,
    )
    result = connector.collect(request())

    assert calls == [
        ["opencli", "x", "search", "--query", "loop engineering", "--limit", "3", "--format", "json"]
    ]
    assert result.warnings == []
    assert result.rows[0]["connector"] == "opencli_bridge"
    assert result.rows[0]["platform"] == "x"
    assert result.rows[0]["title"] == "Loop post"
    assert result.rows[0]["access_mode"] == "opencli_upstream_cli"


def test_opencli_bridge_parses_json_object_results_and_limits_rows():
    def fake_runner(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=(
                '{"results": ['
                '{"title":"One","url":"https://example.com/1","text":"first"},'
                '{"title":"Two","url":"https://example.com/2","text":"second"}'
                "]}"
            ),
            stderr="",
        )

    connector = OpenCliBridgeConnector(
        runner=fake_runner,
        which=lambda command: "/usr/local/bin/opencli" if command == "opencli" else None,
    )
    result = connector.collect(request(max_results=1))

    assert len(result.rows) == 1
    assert result.rows[0]["title"] == "One"


def test_parse_structured_output_accepts_jsonl():
    rows = parse_structured_output(
        '{"title":"One","url":"https://example.com/1"}\n'
        '{"title":"Two","url":"https://example.com/2"}\n'
    )

    assert [row["title"] for row in rows] == ["One", "Two"]


def test_parse_structured_output_ignores_non_json_log_lines():
    rows = parse_structured_output(
        "starting OpenCLI capture\n"
        '{"title":"One","url":"https://example.com/1"}\n'
        "finished capture\n"
    )

    assert [row["title"] for row in rows] == ["One"]


def test_opencli_bridge_plain_text_fallback():
    def fake_runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout="plain visible browser output", stderr="")

    connector = OpenCliBridgeConnector(
        runner=fake_runner,
        which=lambda command: "/usr/local/bin/opencli" if command == "opencli" else None,
    )
    result = connector.collect(request())

    assert result.rows[0]["title"] == "OpenCLI x output"
    assert result.rows[0]["text"] == "plain visible browser output"


def test_opencli_bridge_plain_text_fallback_redacts_headers():
    def fake_runner(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=(
                "Cookie: session=plain-secret; csrftoken=second-secret\n"
                "Authorization: Basic basic-secret\n"
                "visible browser output"
            ),
            stderr="",
        )

    connector = OpenCliBridgeConnector(
        runner=fake_runner,
        which=lambda command: "/usr/local/bin/opencli" if command == "opencli" else None,
    )
    result = connector.collect(request())
    text = result.rows[0]["text"]

    assert "plain-secret" not in text
    assert "second-secret" not in text
    assert "basic-secret" not in text
    assert "[REDACTED]" in text
    assert "visible browser output" in text


def test_opencli_bridge_warns_on_nonzero_exit():
    def fake_runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 2, stdout="", stderr="not authenticated")

    connector = OpenCliBridgeConnector(
        runner=fake_runner,
        which=lambda command: "/usr/local/bin/opencli" if command == "opencli" else None,
    )
    result = connector.collect(request())

    assert result.rows == []
    assert "exited 2" in result.warnings[0]
    assert "not authenticated" in result.warnings[0]


def test_opencli_bridge_redacts_sensitive_command_and_stderr():
    def fake_runner(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            2,
            stdout="",
            stderr="authorization: Bearer super-secret-token",
        )

    connector = OpenCliBridgeConnector(
        runner=fake_runner,
        which=lambda command: "/usr/local/bin/opencli" if command == "opencli" else None,
    )
    result = connector.collect(
        request(
            {
                "command": "opencli x search --token super-secret-token --query {query}",
            }
        )
    )
    rendered = " ".join(result.metadata["commands"][0])
    warnings = " ".join(result.warnings)

    assert "super-secret-token" not in rendered
    assert "super-secret-token" not in warnings
    assert "[REDACTED]" in rendered
    assert "[REDACTED]" in warnings


def test_opencli_bridge_rejects_side_effect_commands():
    calls = []

    def fake_runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")

    connector = OpenCliBridgeConnector(
        runner=fake_runner,
        which=lambda command: "/usr/local/bin/opencli" if command == "opencli" else None,
    )
    result = connector.collect(request({"command": "opencli x post --text hello"}))

    assert calls == []
    assert result.rows == []
    assert "rejected command" in result.warnings[0]
    assert "post" in result.warnings[0]


def test_opencli_bridge_does_not_reject_side_effect_words_inside_query():
    calls = []

    def fake_runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='[{"title":"Buy signal research","url":"https://example.com","text":"read only evidence"}]',
            stderr="",
        )

    connector = OpenCliBridgeConnector(
        runner=fake_runner,
        which=lambda command: "/usr/local/bin/opencli" if command == "opencli" else None,
    )
    result = connector.collect(
        request(
            {
                "query": "buy signal trade policy post market",
                "command": 'opencli x search --query "{query}" --format json',
            }
        )
    )

    assert calls
    assert result.rows[0]["title"] == "Buy signal research"
    assert not any("rejected command" in warning for warning in result.warnings)


def test_opencli_bridge_does_not_reject_url_encoded_query_words():
    calls = []

    def fake_runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='[{"title":"Encoded query result","url":"https://example.com","text":"read only"}]',
            stderr="",
        )

    connector = OpenCliBridgeConnector(
        runner=fake_runner,
        which=lambda command: "/usr/local/bin/opencli" if command == "opencli" else None,
    )
    result = connector.collect(
        request(
            {
                "query": "how to buy and sell stocks",
                "command": "opencli get https://x.example/search?q=how+to+buy+and+sell+stocks",
            }
        )
    )

    assert calls
    assert result.rows[0]["title"] == "Encoded query result"
    assert not any("rejected command" in warning for warning in result.warnings)


def test_opencli_bridge_rejects_executables_outside_allowlist():
    calls = []

    def fake_runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")

    connector = OpenCliBridgeConnector(
        runner=fake_runner,
        which=lambda command: f"/usr/local/bin/{command}",
    )
    result = connector.collect(request({"command": "python -c 'print(123)'"}))

    assert calls == []
    assert result.rows == []
    assert "rejected executable outside allowlist" in result.warnings[0]


def test_opencli_bridge_rejects_path_executable_even_when_basename_is_allowlisted():
    calls = []

    def fake_runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")

    connector = OpenCliBridgeConnector(
        runner=fake_runner,
        which=lambda command: command if command == "/tmp/opencli" else None,
    )
    result = connector.collect(request({"command": "/tmp/opencli x search --query {query}"}))

    assert calls == []
    assert result.rows == []
    assert "rejected executable outside allowlist" in result.warnings[0]


def test_opencli_bridge_rejects_dangerous_opencli_command_terms():
    calls = []

    def fake_runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")

    connector = OpenCliBridgeConnector(
        runner=fake_runner,
        which=lambda command: "/usr/local/bin/opencli" if command == "opencli" else None,
    )
    result = connector.collect(request({"command": "opencli workflow run --query {query}"}))

    assert calls == []
    assert result.rows == []
    assert "rejected command" in result.warnings[0]
    assert "workflow" in result.warnings[0]


def test_opencli_bridge_sanitizes_payload_secrets():
    def fake_runner(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=(
                '{"title":"Visible title","url":"https://example.com",'
                '"text":"Visible evidence token=super-secret-token",'
                '"cookie":"super-secret-cookie",'
                '"metrics":{"authorization":"Bearer super-secret-token","views":3}}'
            ),
            stderr="",
        )

    connector = OpenCliBridgeConnector(
        runner=fake_runner,
        which=lambda command: "/usr/local/bin/opencli" if command == "opencli" else None,
    )
    result = connector.collect(request())
    serialized = str(result.rows[0])

    assert "super-secret-token" not in serialized
    assert "super-secret-cookie" not in serialized
    assert "cookie" not in result.rows[0]
    assert result.rows[0]["metrics"]["views"] == 3


def test_opencli_bridge_payload_metrics_command_cannot_override_bridge_command():
    def fake_runner(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=(
                '{"title":"Visible title","url":"https://example.com",'
                '"text":"Visible evidence",'
                '"metrics":{"command":["opencli","--token","payload-secret-token"],"views":3}}'
            ),
            stderr="",
        )

    connector = OpenCliBridgeConnector(
        runner=fake_runner,
        which=lambda command: "/usr/local/bin/opencli" if command == "opencli" else None,
    )
    result = connector.collect(request())
    serialized = str(result.rows[0])

    assert "payload-secret-token" not in serialized
    assert result.rows[0]["metrics"]["command"] == [
        "opencli",
        "x",
        "search",
        "--query",
        "loop engineering",
        "--limit",
        "3",
        "--format",
        "json",
    ]
