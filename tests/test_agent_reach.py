import subprocess

from research_engine.connectors.agent_reach import (
    AgentReachBridgeConnector,
    render_command_template,
)
from research_engine.models import CollectionRequest


def test_render_command_template_keeps_query_together():
    command = render_command_template(
        'fake-search "{query}" --platform {platform} --limit {max_results}',
        platform="reddit",
        query="DRAM HBM shortage",
        max_results=3,
    )

    assert command == [
        "fake-search",
        "DRAM HBM shortage",
        "--platform",
        "reddit",
        "--limit",
        "3",
    ]


def test_agent_reach_bridge_parses_json_output():
    calls = []

    def fake_which(command):
        return f"/usr/local/bin/{command}" if command == "fake-search" else None

    def fake_runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='[{"title":"Memory cycle","url":"https://example.com/a","text":"HBM tight supply"}]',
            stderr="",
        )

    connector = AgentReachBridgeConnector(
        runner=fake_runner,
        which=fake_which,
        allowed_executables=("fake-search",),
    )
    request = CollectionRequest(
        source={
            "source_id": "agent_reach_bridge",
            "connector": "agent_reach_bridge",
            "query_strategy": {
                "query": "DRAM HBM shortage",
                "platforms": ["reddit"],
                "command_templates": ['fake-search "{query}" --platform {platform}'],
            },
        },
        topic="DRAM HBM shortage",
        run_date="2026-06-21",
        depth="quick",
        max_results=2,
    )

    result = connector.collect(request)

    assert calls == [["fake-search", "DRAM HBM shortage", "--platform", "reddit"]]
    assert result.connector == "agent_reach_bridge"
    assert result.rows[0]["title"] == "Memory cycle"
    assert result.rows[0]["platform"] == "reddit"
    assert result.rows[0]["text"] == "HBM tight supply"


def test_agent_reach_bridge_warns_when_tools_are_missing():
    connector = AgentReachBridgeConnector(runner=lambda *args, **kwargs: None, which=lambda command: None)
    request = CollectionRequest(
        source={
            "source_id": "agent_reach_bridge",
            "connector": "agent_reach_bridge",
            "query_strategy": {"query": "DRAM HBM shortage", "platforms": ["x", "reddit"]},
        },
        topic="DRAM HBM shortage",
        run_date="2026-06-21",
        depth="quick",
        max_results=2,
    )

    result = connector.collect(request)

    assert result.rows == []
    assert "no runnable upstream commands" in result.warnings[0]


def test_agent_reach_bridge_redacts_sensitive_command_and_stderr():
    def fake_which(command):
        return "/usr/local/bin/fake-search" if command == "fake-search" else None

    def fake_runner(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr="authorization: Bearer agent-secret-token",
        )

    connector = AgentReachBridgeConnector(
        runner=fake_runner,
        which=fake_which,
        allowed_executables=("fake-search",),
    )
    request = CollectionRequest(
        source={
            "source_id": "agent_reach_bridge",
            "connector": "agent_reach_bridge",
            "query_strategy": {
                "query": "DRAM HBM shortage",
                "platforms": ["reddit"],
                "command_templates": ['fake-search --token agent-secret-token "{query}"'],
            },
        },
        topic="DRAM HBM shortage",
        run_date="2026-06-21",
        depth="quick",
        max_results=2,
    )

    result = connector.collect(request)

    assert "agent-secret-token" not in " ".join(result.warnings)
    assert "[REDACTED]" in " ".join(result.warnings)


def test_agent_reach_bridge_does_not_reject_side_effect_words_inside_query():
    calls = []

    def fake_which(command):
        return f"/usr/local/bin/{command}" if command == "fake-search" else None

    def fake_runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='[{"title":"Trade policy result","url":"https://example.com","text":"read only"}]',
            stderr="",
        )

    connector = AgentReachBridgeConnector(
        runner=fake_runner,
        which=fake_which,
        allowed_executables=("fake-search",),
    )
    request = CollectionRequest(
        source={
            "source_id": "agent_reach_bridge",
            "connector": "agent_reach_bridge",
            "query_strategy": {
                "query": "buy signal trade policy post market",
                "platforms": ["reddit"],
                "command_templates": ['fake-search "{query}" --platform {platform}'],
            },
        },
        topic="buy signal trade policy post market",
        run_date="2026-06-21",
        depth="quick",
        max_results=2,
    )

    result = connector.collect(request)

    assert calls == [["fake-search", "buy signal trade policy post market", "--platform", "reddit"]]
    assert result.rows[0]["title"] == "Trade policy result"
    assert not any("rejected command" in warning for warning in result.warnings)


def test_agent_reach_bridge_rejects_executables_outside_allowlist():
    calls = []

    def fake_runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")

    connector = AgentReachBridgeConnector(
        runner=fake_runner,
        which=lambda command: f"/usr/local/bin/{command}",
    )
    request = CollectionRequest(
        source={
            "source_id": "agent_reach_bridge",
            "connector": "agent_reach_bridge",
            "query_strategy": {
                "query": "market research",
                "platforms": ["reddit"],
                "command_templates": ["python -c 'print(123)'"],
            },
        },
        topic="market research",
        run_date="2026-06-21",
        depth="quick",
        max_results=2,
    )

    result = connector.collect(request)

    assert calls == []
    assert result.rows == []
    assert "rejected executable outside allowlist" in result.warnings[0]


def test_agent_reach_bridge_rejects_child_command_execution_flags():
    calls = []

    def fake_runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")

    connector = AgentReachBridgeConnector(
        runner=fake_runner,
        which=lambda command: f"/usr/local/bin/{command}",
    )
    request = CollectionRequest(
        source={
            "source_id": "agent_reach_bridge",
            "connector": "agent_reach_bridge",
            "query_strategy": {
                "query": "video research",
                "platforms": ["youtube"],
                "command_templates": ['yt-dlp --exec "sh -c id" "ytsearch1:{query}"'],
            },
        },
        topic="video research",
        run_date="2026-06-21",
        depth="quick",
        max_results=2,
    )

    result = connector.collect(request)

    assert calls == []
    assert result.rows == []
    assert "rejected command" in result.warnings[0]
    assert "--exec" in result.warnings[0]


def test_agent_reach_bridge_query_cannot_mask_execution_flags():
    calls = []

    def fake_runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")

    connector = AgentReachBridgeConnector(
        runner=fake_runner,
        which=lambda command: f"/usr/local/bin/{command}",
    )
    request = CollectionRequest(
        source={
            "source_id": "agent_reach_bridge",
            "connector": "agent_reach_bridge",
            "query_strategy": {
                "query": "--exec",
                "platforms": ["youtube"],
                "command_templates": ['yt-dlp --exec id "ytsearch1:{query}"'],
            },
        },
        topic="--exec",
        run_date="2026-06-21",
        depth="quick",
        max_results=2,
    )

    result = connector.collect(request)

    assert calls == []
    assert result.rows == []
    assert "rejected command" in result.warnings[0]
    assert "--exec" in result.warnings[0]


def test_agent_reach_bridge_allows_doctor_advertised_xhs_and_xq_tools():
    calls = []

    def fake_runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='[{"title":"Platform result","url":"https://example.com","text":"visible"}]',
            stderr="",
        )

    connector = AgentReachBridgeConnector(
        runner=fake_runner,
        which=lambda command: f"/usr/local/bin/{command}" if command in {"xhs", "xq"} else None,
    )
    request = CollectionRequest(
        source={
            "source_id": "agent_reach_bridge",
            "connector": "agent_reach_bridge",
            "query_strategy": {
                "query": "consumer memory discussion",
                "platforms": ["xhs", "xq"],
                "command_templates": ['{platform} search "{query}" --limit {max_results}'],
            },
        },
        topic="consumer memory discussion",
        run_date="2026-06-21",
        depth="quick",
        max_results=2,
    )

    result = connector.collect(request)

    assert calls == [
        ["xhs", "search", "consumer memory discussion", "--limit", "2"],
        ["xq", "search", "consumer memory discussion", "--limit", "2"],
    ]
    assert len(result.rows) == 2
    assert result.warnings == []
