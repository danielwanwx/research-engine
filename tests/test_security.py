from research_engine.security import (
    command_risk_terms,
    redact_command,
    redact_text,
    sanitize_for_artifact,
)


def test_redact_text_redacts_common_url_secret_params():
    text = redact_text(
        "https://example.com/path?access_token=access-secret&sessionid=session-secret&ok=1"
    )

    assert "access-secret" not in text
    assert "session-secret" not in text
    assert "ok=1" in text
    assert "[REDACTED]" in text


def test_redact_command_hides_next_arg_secrets_and_executable_paths():
    command = redact_command(["/tmp/private/opencli", "--token", "plain-secret", "--query", "visible"])

    assert command == ["opencli", "--token", "[REDACTED]", "--query", "visible"]


def test_sanitize_for_artifact_redacts_command_like_lists():
    payload = sanitize_for_artifact(
        {
            "metrics": {
                "command": ["opencli", "--token", "plain-secret", "--query", "visible"],
                "views": 3,
            }
        }
    )

    assert payload["metrics"]["command"] == [
        "opencli",
        "--token",
        "[REDACTED]",
        "--query",
        "visible",
    ]
    assert payload["metrics"]["views"] == 3


def test_command_risk_ignores_url_encoded_query_values():
    risks = command_risk_terms(
        ["opencli", "https://x.example/search?q=how+to+buy+and+sell+stocks"],
        ignored_values=["how to buy and sell stocks"],
    )

    assert risks == []


def test_command_risk_ignores_dangerous_words_when_they_are_query_values():
    risks = command_risk_terms(
        ["opencli", "search", "api workflow run analysis"],
        ignored_values=["api workflow run analysis"],
    )

    assert risks == []


def test_command_risk_rejects_execution_flags():
    risks = command_risk_terms(["yt-dlp", "--exec", "sh -c id", "ytsearch1:test"])

    assert "--exec" in risks
    assert "sh" in risks


def test_command_risk_does_not_allow_query_to_mask_dangerous_flags():
    risks = command_risk_terms(
        ["yt-dlp", "--exec", "id", "ytsearch1:--exec"],
        ignored_values=["--exec"],
    )

    assert "--exec" in risks
