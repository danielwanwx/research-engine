from research_engine.security import (
    command_risk_terms,
    redact_command,
    redact_text,
    sanitize_for_artifact,
    sensitive_value_paths,
)


def test_redact_text_redacts_common_url_secret_params():
    text = redact_text(
        "https://example.com/path?access_token=access-secret&sessionid=session-secret&ok=1"
    )

    assert "access-secret" not in text
    assert "session-secret" not in text
    assert "ok=1" in text
    assert "[REDACTED]" in text


def test_redact_text_preserves_prior_authorization_policy_text():
    text = "Prior authorization: required for CPT 99213 documentation."

    assert redact_text(text) == text


def test_redact_text_preserves_noncredential_authorization_prose():
    text = (
        "Insurance authorization: required for claim processing. "
        "Payment authorization: pending merchant review."
    )

    assert redact_text(text) == text
    assert sensitive_value_paths({"text": text}) == []


def test_sanitize_preserves_prior_authorization_fields():
    payload = sanitize_for_artifact(
        {
            "prior_authorization": "required for CPT 99213",
            "pre_authorization_status": "required",
            "preauthorization_status": "pending clinical review",
            "preauthorization_policy": "payer-specific documentation required",
            "preauthorization_token": "preauth-secret-token",
            "authorization": "Bearer auth-secret-token",
            "authorization_header": "Bearer auth-secret-token",
        }
    )

    assert payload["prior_authorization"] == "required for CPT 99213"
    assert payload["pre_authorization_status"] == "required"
    assert payload["preauthorization_status"] == "pending clinical review"
    assert payload["preauthorization_policy"] == "payer-specific documentation required"
    assert "preauthorization_token" not in payload
    assert "authorization" not in payload
    assert "authorization_header" not in payload


def test_redact_text_redacts_authorization_credentials():
    bearer = redact_text("Authorization: Bearer auth-secret-token")
    basic = redact_text("Authorization: Basic basic-secret-token")
    token = redact_text("Authorization: Token token-secret-value")
    oauth = redact_text("Authorization: OAuth oauth-secret-token")
    digest = redact_text("Authorization: Digest digest-secret-token")
    api_key = redact_text("Authorization: ApiKey api-secret-token")

    assert "auth-secret-token" not in bearer
    assert "basic-secret-token" not in basic
    assert "token-secret-value" not in token
    assert "oauth-secret-token" not in oauth
    assert "digest-secret-token" not in digest
    assert "api-secret-token" not in api_key
    assert bearer == "authorization=Bearer [REDACTED]"
    assert basic == "authorization=Basic [REDACTED]"
    assert token == "authorization=Token [REDACTED]"
    assert oauth == "authorization=OAuth [REDACTED]"
    assert digest == "authorization=Digest [REDACTED]"
    assert api_key == "authorization=ApiKey [REDACTED]"


def test_redact_text_redacts_raw_cloud_github_and_jwt_tokens():
    raw = (
        "aws=AKIAIOSFODNN7EXAMPLE "
        "github=ghp_abcdefghijklmnopqrstuvwxyz123456 "
        "jwt=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signaturesecret12345"
    )

    text = redact_text(raw)

    assert "AKIAIOSFODNN7EXAMPLE" not in text
    assert "ghp_abcdefghijklmnopqrstuvwxyz123456" not in text
    assert "signaturesecret12345" not in text
    assert text.count("[REDACTED]") == 3


def test_redact_text_redacts_compound_sensitive_assignments():
    text = redact_text(
        "RuntimeError: client_secret=client-secret-value "
        "request failed: aws_secret_access_key=aws-secret-value "
        "stripe_api_key=stripe-secret-value prior_authorization=required "
        "embedded header Authorization: Basic dXNlcjpwYXNz"
    )

    assert "client-secret-value" not in text
    assert "aws-secret-value" not in text
    assert "stripe-secret-value" not in text
    assert "dXNlcjpwYXNz" not in text
    assert "prior_authorization=required" in text


def test_redact_command_hides_next_arg_secrets_and_executable_paths():
    command = redact_command(
        ["/tmp/private/opencli", "--token", "plain-secret", "--query", "visible"]
    )

    assert command == ["opencli", "--token", "[REDACTED]", "--query", "visible"]


def test_redact_text_keeps_split_flag_match_out_of_preceding_secret_value():
    text = redact_text(
        "fake client_secret=smoke-secret --token split-secret "
        "--client-secret compound-flag-secret {query}"
    )

    assert "smoke-secret" not in text
    assert "split-secret" not in text
    assert "compound-flag-secret" not in text


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


def test_sensitive_value_paths_detects_secret_like_strings():
    payload = {
        "text": "Visible evidence Cookie: sessionid=session-secret",
        "metadata": {"note": "authorization: Bearer auth-secret"},
    }

    paths = sensitive_value_paths(payload)

    assert "text" in paths
    assert "metadata.note" in paths


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
