import json
import subprocess

from research_engine.cli import main
from research_engine.doctor import (
    check_command,
    check_login_browser,
    render_doctor_text,
    run_doctor,
)
from research_engine.state import (
    CONNECTOR_CAPABILITIES_FILE,
    read_state_json,
    write_state_json,
)


def test_run_doctor_writes_missing_optional_capabilities(tmp_path):
    report = run_doctor(
        target="agentreach",
        state_dir=tmp_path,
        which=lambda command: None,
    )

    assert report["status"] == "complete_with_warnings"
    assert report["summary"]["required_failure_count"] == 0
    assert report["summary"]["optional_missing_count"] >= 1
    assert (tmp_path / CONNECTOR_CAPABILITIES_FILE).exists()
    stored = json.loads((tmp_path / CONNECTOR_CAPABILITIES_FILE).read_text(encoding="utf-8"))
    assert stored["artifact_path"] == str(tmp_path / CONNECTOR_CAPABILITIES_FILE)
    assert any(check["id"] == "command:twitter" for check in report["checks"])


def test_check_command_reads_version_from_available_tool():
    def fake_runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout="opencli 1.2.3\n", stderr="")

    check = check_command(
        "opencli",
        label="OpenCLI",
        group="opencli",
        connector_ids=("opencli_bridge",),
        version_args=("--version",),
        runner=fake_runner,
        which=lambda command: "/usr/local/bin/opencli",
    )

    assert check.available is True
    assert check.path == "/usr/local/bin/opencli"
    assert check.version == "opencli 1.2.3"
    assert check.metadata["connector_ids"] == ["opencli_bridge"]


def test_cli_doctor_outputs_json_and_writes_state(tmp_path, capsys):
    exit_code = main(
        [
            "doctor",
            "opencli",
            "--state-dir",
            str(tmp_path),
            "--format",
            "json",
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["target"] == "opencli"
    assert (tmp_path / CONNECTOR_CAPABILITIES_FILE).exists()


def test_render_doctor_text_includes_status(tmp_path):
    report = run_doctor(target="opencli", state_dir=tmp_path, which=lambda command: None)
    text = render_doctor_text(report)

    assert "Research Engine doctor" in text
    assert "Status:" in text
    assert "OpenCLI" in text


def test_state_json_round_trips(tmp_path):
    path = write_state_json(tmp_path, "example.json", {"ok": True})

    assert path == tmp_path / "example.json"
    assert read_state_json(tmp_path, "example.json") == {"ok": True}
    assert read_state_json(tmp_path, "missing.json") == {}


def test_browser_doctor_reports_browser_specific_checks(tmp_path):
    report = run_doctor(target="browser", state_dir=tmp_path, write=False)

    ids = {check["id"] for check in report["checks"]}
    assert report["target"] == "browser"
    assert "python_import:playwright" in ids
    assert "browser:chromium" in ids
    assert "browser:login_chrome" in ids
    assert "browser:gui" in ids


def test_login_browser_doctor_reports_normal_chrome_separately():
    available = check_login_browser(lambda: "/Applications/Google Chrome")
    missing = check_login_browser(lambda: "")

    assert available.available
    assert available.id == "browser:login_chrome"
    assert not missing.available
    assert "RESEARCH_ENGINE_LOGIN_BROWSER" in missing.warning
