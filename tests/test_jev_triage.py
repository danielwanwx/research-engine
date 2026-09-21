from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from research_engine.cli import main
from research_engine.jev_triage import (
    JevServiceError,
    JevTriageError,
    MAX_EVIDENCE_ITEMS,
    MAX_INPUT_ROWS,
    load_evidence_rows,
    triage_public_evidence,
)


def public_row(index: int, **overrides: Any) -> dict[str, Any]:
    row = {
        "evidence_id": f"ev-{index:04d}",
        "access_mode": "public_url_refetch",
        "url": f"https://example.com/evidence/{index}?token=discard-me",
        "title": f"Public evidence {index}",
        "source_kind": "canonical_web_page",
        "text": f"Public evidence item {index} about inference runtimes.",
    }
    row.update(overrides)
    return row


def test_single_canonical_evidence_jsonl_row_batches_nouls_and_projects_only_known_fields():
    row = public_row(
        1,
        text="Visible public text api_key=not-forwarded-secret",
        unknown_metadata={"authorization": "do-not-forward"},
    )
    rows = load_evidence_rows(stdin=io.StringIO(json.dumps(row) + "\n"))
    sent: dict[str, Any] = {}

    def transport(payload: dict[str, Any], api_key: str, timeout: float) -> dict[str, Any]:
        sent["payload"] = payload
        assert api_key == "test-key"
        assert timeout > 0
        return {
            "model": "jev-1.13.0",
            "answers": {"item_1": {"type": "noul", "noul": 0.83}},
            "usage": {"input_tokens": 41, "output_tokens": 7},
        }

    result = triage_public_evidence(
        topic="Inference runtimes",
        rows=rows,
        allow_jev=True,
        api_key="test-key",
        transport=transport,
    )

    assert result["status"] == "complete"
    assert result["usage"] == {"input_tokens": 41, "output_tokens": 7}
    assert result["judgments"][0]["noul"] == 0.83
    assert result["events"][1]["type"] == "jev_request_started"
    assert result["events"][1]["question_count"] == 1
    forwarded = sent["payload"]
    assert set(forwarded["state"]["evidence"][0]) == {
        "evidence_id",
        "title",
        "url",
        "source_kind",
        "text",
    }
    assert forwarded["state"]["evidence"][0]["url"] == "https://example.com/evidence/1"
    serialized = json.dumps({"result": result, "request": forwarded})
    assert "not-forwarded-secret" not in serialized
    assert "do-not-forward" not in serialized


def test_private_bridge_marker_overrides_public_access_mode_without_calling_provider():
    calls = 0

    def transport(payload: dict[str, Any], api_key: str, timeout: float) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {}

    result = triage_public_evidence(
        topic="Inference runtimes",
        rows=[public_row(1, source_bridge="authenticated_browser")],
        allow_jev=True,
        api_key="test-key",
        transport=transport,
    )

    assert result["status"] == "failed"
    assert result["error_code"] == "no_eligible_public_evidence"
    assert calls == 0


def test_triage_limits_batched_items_and_records_omitted_rows():
    rows = [public_row(index) for index in range(1, MAX_EVIDENCE_ITEMS + 3)]
    seen: dict[str, Any] = {}

    def transport(payload: dict[str, Any], api_key: str, timeout: float) -> dict[str, Any]:
        seen["questions"] = payload["questions"]
        return {
            "model": "jev-1.13.0",
            "answers": {
                f"item_{index}": {"type": "noul", "noul": 0.5}
                for index in range(1, MAX_EVIDENCE_ITEMS + 1)
            },
            "usage": {"input_tokens": 80, "output_tokens": 20},
        }

    result = triage_public_evidence(
        topic="Inference runtimes",
        rows=rows,
        allow_jev=True,
        api_key="test-key",
        transport=transport,
    )

    assert len(seen["questions"]) == MAX_EVIDENCE_ITEMS
    assert result["selection"]["selected_rows"] == MAX_EVIDENCE_ITEMS
    assert result["selection"]["not_selected_rows"] == 2
    assert {entry["reason"] for entry in result["selection"]["skipped"]} == {
        "evidence_item_limit"
    }


def test_loader_rejects_more_than_bounded_input_rows():
    envelope = {"schema_version": "jev_triage_input.v1", "evidence": [public_row(index) for index in range(MAX_INPUT_ROWS + 1)]}
    with pytest.raises(JevTriageError, match="evidence_row_limit_exceeded"):
        load_evidence_rows(stdin=io.StringIO(json.dumps(envelope)))


def test_provider_failure_is_terminal_and_does_not_echo_provider_body_or_key():
    def transport(payload: dict[str, Any], api_key: str, timeout: float) -> dict[str, Any]:
        raise JevServiceError("rate_limited")

    result = triage_public_evidence(
        topic="Inference runtimes",
        rows=[public_row(1)],
        allow_jev=True,
        api_key="synthetic-secret-key",
        transport=transport,
    )

    assert result["status"] == "failed"
    assert result["error_code"] == "rate_limited"
    assert result["usage"] is None
    assert result["events"][-1] == {"type": "triage_finished", "at": result["events"][-1]["at"], "status": "failed"}
    assert "synthetic-secret-key" not in json.dumps(result)


def test_cli_file_path_honors_prompt_key_without_reading_stdin(tmp_path, monkeypatch, capsys):
    path = Path(tmp_path) / "evidence.jsonl"
    path.write_text(json.dumps(public_row(1)) + "\n", encoding="utf-8")
    calls: dict[str, Any] = {}

    def resolve(*, prompt_key: bool = False, **kwargs: Any) -> str:
        calls["prompt_key"] = prompt_key
        return "test-key"

    def transport(payload: dict[str, Any], api_key: str, timeout: float) -> dict[str, Any]:
        calls["request"] = payload
        return {
            "model": "jev-1.13.0",
            "answers": {"item_1": {"type": "noul", "noul": 0.72}},
            "usage": {"input_tokens": 33, "output_tokens": 5},
        }

    monkeypatch.setattr("research_engine.jev_triage.resolve_api_key", resolve)
    monkeypatch.setattr("research_engine.jev_triage.post_system_one", transport)

    exit_code = main(
        [
            "jev-triage",
            "--topic",
            "Inference runtimes",
            "--allow-jev",
            "--prompt-key",
            "--evidence",
            str(path),
        ]
    )

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert calls["prompt_key"] is True
    assert rendered["status"] == "complete"
    assert calls["request"]["model"] == "jev-latest"


def test_cli_requires_explicit_jev_consent_before_reading_evidence(tmp_path, capsys):
    missing_path = Path(tmp_path) / "missing.jsonl"

    exit_code = main(
        [
            "jev-triage",
            "--topic",
            "Inference runtimes",
            "--evidence",
            str(missing_path),
        ]
    )

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert rendered["error_code"] == "jev_consent_required"
