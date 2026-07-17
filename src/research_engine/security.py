"""Artifact-safety helpers for connector outputs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
from pathlib import Path
import re
from typing import Any
from urllib.parse import quote, quote_plus


REDACTED = "[REDACTED]"

SENSITIVE_KEY_TOKENS = {
    "access_token",
    "apikey",
    "api_key",
    "auth",
    "auth_token",
    "authorization",
    "bearer",
    "cookie",
    "credential",
    "credentials",
    "csrf_token",
    "csrftoken",
    "id_token",
    "passwd",
    "password",
    "refresh_token",
    "secret",
    "session",
    "session_id",
    "sessionid",
    "sid",
    "storage_state",
    "token",
    "xsrf_token",
}
DOMAIN_SAFE_KEY_PREFIXES = (
    "prior_authorization",
    "pre_authorization",
    "preauthorization",
)
DOMAIN_SAFE_SENSITIVE_SUFFIXES = (
    "_api_key",
    "_apikey",
    "_auth",
    "_cookie",
    "_credential",
    "_credentials",
    "_password",
    "_secret",
    "_session",
    "_session_id",
    "_sessionid",
    "_sid",
    "_token",
)
SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)(?<!prior )(?<!pre )\b("
    r"(?:[a-z0-9]+[_-])*(?:auth|cookie|set-cookie|bearer|token|secret|"
    r"password|passwd|api[_-]?key|access[_-]?token|auth[_-]?token|id[_-]?token|"
    r"refresh[_-]?token|storage[_-]?state|credential|session(?:id|[_-]?id)?)"
    r"(?:[_-][a-z0-9]+)*)\s*([:=])\s*([^\s,;&]+)"
)
SENSITIVE_HEADER_RE = re.compile(r"(?im)\b(cookie|set-cookie)\s*[:=]\s*[^\r\n]+")
AUTH_CREDENTIAL_HEADER_RE = re.compile(
    r"(?i)(?<!prior )(?<!pre )\bauthorization\s*[:=]\s*"
    r"(Basic|Bearer|Digest|OAuth|Token|ApiKey)\s+([^\s,;]+)"
)
AUTH_DIRECT_ASSIGNMENT_RE = re.compile(
    r"(?i)\bauthorization\s*=\s*"
    r"(?!(?:Basic|Bearer|Digest|OAuth|Token|ApiKey)\b)[^\s,;&]+"
)
BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
COMMON_SECRET_RE = re.compile(
    r"\b(?:sk|xoxb|xoxp)-[A-Za-z0-9_=-]{8,}\b|"
    r"\bghp_[A-Za-z0-9_]{20,}\b|"
    r"\bgithub_pat_[A-Za-z0-9_]{20,}\b|"
    r"\bAKIA[0-9A-Z]{16}\b|"
    r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
)
SENSITIVE_URL_PARAM_RE = re.compile(
    r"(?i)([?&;](?:access_token|auth_token|id_token|refresh_token|sessionid|"
    r"session_id|sid|csrftoken|csrf_token|xsrf_token|token|api_key|apikey|"
    r"password|secret)=)[^&#\s]+"
)
SENSITIVE_FLAG_NAME_PATTERN = (
    r"(?:[a-z0-9]+[_-])*(?:cookie|set[_-]cookie|authorization|auth|bearer|token|"
    r"secret|password|passwd|api[_-]?key|storage[_-]?state|credential|"
    r"session(?:id|[_-]?id)?)(?:[_-][a-z0-9]+)*"
)
SENSITIVE_FLAG_VALUE_TEXT_RE = re.compile(
    rf"(?i)(?<!\S)(--?({SENSITIVE_FLAG_NAME_PATTERN})\s+)([^\s]+)"
)
SENSITIVE_FLAG_RE = re.compile(
    rf"^--?({SENSITIVE_FLAG_NAME_PATTERN})(?:=.*)?$",
    re.IGNORECASE,
)

SIDE_EFFECT_TERMS = {
    "buy",
    "comment",
    "delete",
    "dm",
    "follow",
    "like",
    "message",
    "order",
    "post",
    "reply",
    "repost",
    "retweet",
    "sell",
    "send",
    "submit",
    "trade",
    "tweet",
    "unfollow",
    "upload",
}

DANGEROUS_COMMAND_TERMS = {
    "alias",
    "automation",
    "bash",
    "eval",
    "exec",
    "execute",
    "extension",
    "install",
    "node",
    "osascript",
    "perl",
    "python",
    "ruby",
    "run",
    "script",
    "shell",
    "sh",
    "workflow",
    "zsh",
}

DANGEROUS_FLAGS = {
    "--command",
    "--config-location",
    "--downloader",
    "--downloader-args",
    "--eval",
    "--exec",
    "--exec-before-download",
    "--execute",
    "--external-downloader",
    "--external-downloader-args",
    "--postprocessor-args",
    "--run",
    "--script",
    "--shell",
    "--use-postprocessor",
}

COMMAND_LIKE_KEYS = {"argv", "cmd", "command", "command_argv", "command_line"}


def is_sensitive_key(key: Any) -> bool:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", str(key).strip().lower()).strip("_")
    if any(normalized.startswith(prefix) for prefix in DOMAIN_SAFE_KEY_PREFIXES):
        if normalized.endswith(DOMAIN_SAFE_SENSITIVE_SUFFIXES):
            return True
        return False
    if normalized.endswith(DOMAIN_SAFE_SENSITIVE_SUFFIXES):
        return True
    if normalized in SENSITIVE_KEY_TOKENS:
        return True
    if normalized.startswith(("authorization_", "auth_header", "authentication_header")):
        return True
    tokens = {token for token in normalized.split("_") if token}
    token_sensitive_keys = SENSITIVE_KEY_TOKENS - {"authorization", "auth"}
    return bool(tokens & token_sensitive_keys)


def redact_assignment(match: re.Match[str]) -> str:
    key = match.group(1)
    return f"{key}={REDACTED}" if is_sensitive_key(key) else match.group(0)


def redact_flag_value(match: re.Match[str]) -> str:
    if not is_sensitive_key(match.group(2)):
        return match.group(0)
    return f"{match.group(1)}{REDACTED}"


def redact_text(value: Any) -> str:
    text = str(value)
    text = SENSITIVE_HEADER_RE.sub(lambda match: f"{match.group(1)}={REDACTED}", text)
    text = AUTH_CREDENTIAL_HEADER_RE.sub(
        lambda match: f"authorization={match.group(1)} {REDACTED}",
        text,
    )
    text = AUTH_DIRECT_ASSIGNMENT_RE.sub(f"authorization={REDACTED}", text)
    text = BEARER_RE.sub(f"Bearer {REDACTED}", text)
    text = SENSITIVE_URL_PARAM_RE.sub(lambda match: f"{match.group(1)}{REDACTED}", text)
    text = SENSITIVE_FLAG_VALUE_TEXT_RE.sub(redact_flag_value, text)
    text = SENSITIVE_ASSIGNMENT_RE.sub(redact_assignment, text)
    text = COMMON_SECRET_RE.sub(REDACTED, text)
    return text


def sanitize_for_artifact(value: Any) -> Any:
    if isinstance(value, Mapping):
        cleaned: dict[str, Any] = {}
        for key, nested in value.items():
            if is_sensitive_key(key):
                continue
            if str(key).lower() in COMMAND_LIKE_KEYS:
                if isinstance(nested, Sequence) and not isinstance(nested, str):
                    cleaned[str(key)] = redact_command(nested)
                else:
                    cleaned[str(key)] = redact_text(nested)
                continue
            cleaned[str(key)] = sanitize_for_artifact(nested)
        return cleaned
    if isinstance(value, (list, tuple)):
        return [sanitize_for_artifact(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def sensitive_paths(value: Any, *, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key)
            path = f"{prefix}.{key_text}" if prefix else key_text
            if is_sensitive_key(key_text):
                paths.append(path)
                continue
            paths.extend(sensitive_paths(nested, prefix=path))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            paths.extend(sensitive_paths(nested, prefix=f"{prefix}[{index}]"))
    return paths


def sensitive_value_paths(value: Any, *, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key)
            path = f"{prefix}.{key_text}" if prefix else key_text
            paths.extend(sensitive_value_paths(nested, prefix=path))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            paths.extend(sensitive_value_paths(nested, prefix=f"{prefix}[{index}]"))
    elif isinstance(value, str) and redact_text(value) != value:
        paths.append(prefix or "<value>")
    return paths


def redact_command(command: Sequence[Any]) -> list[str]:
    redacted: list[str] = []
    redact_next = False
    for index, part in enumerate(command):
        text = str(part)
        if index == 0 and Path(text).name != text:
            redacted.append(Path(text).name or REDACTED)
            continue
        if redact_next:
            redacted.append(REDACTED)
            redact_next = False
            continue
        sensitive_flag = SENSITIVE_FLAG_RE.match(text)
        if sensitive_flag and is_sensitive_key(sensitive_flag.group(1)):
            if "=" in text:
                key = text.split("=", 1)[0]
                redacted.append(f"{key}={REDACTED}")
            else:
                redacted.append(text)
                redact_next = True
            continue
        redacted.append(redact_text(text))
    return redacted


def allowed_executable(command: Sequence[Any], allowed: Sequence[str]) -> str | None:
    if not command:
        return None
    executable_text = str(command[0])
    executable = Path(executable_text).name
    if executable != executable_text:
        return None
    allowed_names = {Path(str(item)).name for item in allowed}
    return executable if executable in allowed_names else None


def ignored_value_variants(values: Sequence[Any]) -> set[str]:
    variants: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        variants.update(
            {
                text.lower(),
                quote_plus(text).lower(),
                quote(text).lower(),
                text.replace(" ", "+").lower(),
                text.replace(" ", "%20").lower(),
            }
        )
    return variants


def command_text_without_ignored_values(part: Any, ignored_values: Sequence[Any]) -> str:
    text = str(part).lower()
    for ignored_text in ignored_value_variants(ignored_values):
        text = text.replace(ignored_text, " ")
    return text


def side_effect_terms(command: Sequence[Any], *, ignored_values: Sequence[Any] = ()) -> list[str]:
    matched: set[str] = set()
    for part in command:
        text = command_text_without_ignored_values(part, ignored_values)
        tokens = [token for token in re.split(r"[^a-zA-Z0-9]+", text) if token]
        matched.update(token for token in tokens if token in SIDE_EFFECT_TERMS)
    return sorted(matched)


def command_risk_terms(command: Sequence[Any], *, ignored_values: Sequence[Any] = ()) -> list[str]:
    matched = set(side_effect_terms(command, ignored_values=ignored_values))
    for part in command:
        original_text = str(part).lower()
        stripped = original_text.strip()
        flag_name = stripped.split("=", 1)[0]
        if flag_name in DANGEROUS_FLAGS:
            matched.add(flag_name)
        if stripped.startswith("-"):
            continue
        text = command_text_without_ignored_values(part, ignored_values)
        tokens = [token for token in re.split(r"[^a-zA-Z0-9]+", text) if token]
        matched.update(token for token in tokens if token in DANGEROUS_COMMAND_TERMS)
    return sorted(matched)


def artifact_path_ref(path_value: Any) -> dict[str, str]:
    path = Path(str(path_value)).expanduser()
    try:
        stable_path = str(path.resolve(strict=False))
    except OSError:
        stable_path = str(path)
    digest = hashlib.sha256(stable_path.encode("utf-8")).hexdigest()[:12]
    return {"name": path.name, "path_hash": digest}


def format_artifact_path_ref(path_value: Any, *, line_number: int | None = None) -> str:
    ref = artifact_path_ref(path_value)
    text = f"{ref['name']}#{ref['path_hash']}"
    if line_number is not None:
        text = f"{text}:{line_number}"
    return text
