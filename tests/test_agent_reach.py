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

    connector = AgentReachBridgeConnector(runner=fake_runner, which=fake_which)
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
