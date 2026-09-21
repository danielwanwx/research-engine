"""Bounded, advisory Jev triage for already-collected public evidence.

This module intentionally sits outside the research runner.  It projects a
small allowlisted subset of public evidence to TypeSafe for relevance judgments;
it never fetches a source, changes a canonical evidence artifact, or decides
whether an item is verified or eligible for a claim.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import getpass
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from research_engine.models import utc_now
from research_engine.security import redact_text


INPUT_SCHEMA = "jev_triage_input.v1"
RESULT_SCHEMA = "jev_triage_result.v1"
TYPESAFE_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
JEV_MODEL = "jev-latest"
KEYCHAIN_SERVICE = "typesafe-ai-jev"

MAX_INPUT_BYTES = 128 * 1024
MAX_INPUT_ROWS = 32
MAX_EVIDENCE_ITEMS = 8
MAX_TOPIC_CHARS = 500
MAX_EVIDENCE_ID_CHARS = 128
MAX_TITLE_CHARS = 500
MAX_URL_CHARS = 2048
MAX_SOURCE_TEXT_CHARS = 3_000
MAX_RESPONSE_BYTES = 128 * 1024
REQUEST_TIMEOUT_SECONDS = 30.0

# These are the public modes emitted by the current first-party public
# connectors.  Logged-in/browser/external/agent-reach modes are deliberately
# excluded; triage has an explicit public-evidence-only boundary.
PUBLIC_ACCESS_MODES = frozenset(
    {
        "anysearch_public_search",
        "official_ashby_api_and_final_url",
        "official_company_search_page",
        "official_custom_site_api_and_final_url",
        "official_greenhouse_api_and_final_url",
        "official_lever_api_and_final_url",
        "public_discovery_refetch",
        "public_github_api",
        "public_official_endpoints",
        "public_repair_refetch",
        "public_search_page_fetch",
        "public_url_refetch",
        "xai_public_search_citation",
        "xai_web_search",
    }
)

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SAFE_MODEL = re.compile(r"^jev-(?:latest|[0-9]+(?:\.[0-9]+){1,3}(?:[-.][A-Za-z0-9]+)?)$")
_BLOCKED_HOST_SUFFIXES = (".local", ".internal", ".localhost")
_PRIVATE_SOURCE_MARKERS = frozenset(
    {
        "agent_reach",
        "authenticated",
        "auth",
        "bridge",
        "browser",
        "external",
        "logged_in",
        "opencli",
        "private",
    }
)


class JevTriageError(ValueError):
    """A safe, machine-readable local triage error."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class JevServiceError(RuntimeError):
    """A provider failure with no provider-body disclosure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class PreparedEvidence:
    evidence_id: str
    title: str
    url: str
    source_kind: str
    access_mode: str
    text: str
    source_text_chars: int
    forwarded_text_chars: int
    text_truncated: bool

    def state_value(self) -> dict[str, str]:
        return {
            "evidence_id": self.evidence_id,
            "title": self.title,
            "url": self.url,
            "source_kind": self.source_kind,
            "text": self.text,
        }

    def result_value(self, *, noul: float) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "title": self.title,
            "url": self.url,
            "source_kind": self.source_kind,
            "access_mode": self.access_mode,
            "noul": noul,
            "source_text_chars": self.source_text_chars,
            "forwarded_text_chars": self.forwarded_text_chars,
            "text_truncated": self.text_truncated,
        }


Transport = Callable[[dict[str, Any], str, float], Mapping[str, Any]]


class _NoRedirectHandler(HTTPRedirectHandler):
    """Fail closed rather than forwarding the Authorization header to a redirect target."""

    def redirect_request(  # type: ignore[override]
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Request:
        raise HTTPError(req.full_url, code, "redirect_blocked", headers, fp)


_NO_REDIRECT_OPENER = build_opener(_NoRedirectHandler())


def load_evidence_rows(
    *,
    evidence_path: Path | None = None,
    stdin: Any | None = None,
) -> list[dict[str, Any]]:
    """Load a bounded input envelope or a bounded canonical evidence JSONL file."""

    if (evidence_path is None) == (stdin is None):
        raise JevTriageError("input_source_required")
    if evidence_path is not None:
        try:
            with evidence_path.open("rb") as handle:
                raw = handle.read(MAX_INPUT_BYTES + 1)
        except OSError as exc:
            raise JevTriageError("evidence_input_unavailable") from exc
    else:
        raw = _read_bounded_stdin(stdin)
    if len(raw) > MAX_INPUT_BYTES:
        raise JevTriageError("evidence_input_too_large")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise JevTriageError("evidence_input_not_utf8") from exc
    return _parse_evidence_text(text)


def _read_bounded_stdin(stdin: Any) -> bytes:
    if stdin is None:
        raise JevTriageError("input_source_required")
    source = getattr(stdin, "buffer", stdin)
    value = source.read(MAX_INPUT_BYTES + 1)
    if isinstance(value, bytes):
        return value
    return str(value).encode("utf-8")


def _parse_evidence_text(text: str) -> list[dict[str, Any]]:
    if not text.strip():
        raise JevTriageError("evidence_input_empty")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return _parse_jsonl_rows(text)
    if isinstance(payload, Mapping):
        schema = payload.get("schema_version")
        if schema not in {None, INPUT_SCHEMA}:
            raise JevTriageError("unsupported_evidence_schema")
        if "evidence" in payload:
            payload = payload.get("evidence")
        elif _is_canonical_evidence_row(payload):
            payload = [payload]
    if not isinstance(payload, list):
        raise JevTriageError("evidence_envelope_required")
    return _validate_input_rows(payload)


def _parse_jsonl_rows(text: str) -> list[dict[str, Any]]:
    rows: list[Any] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise JevTriageError("evidence_jsonl_invalid") from exc
    return _validate_input_rows(rows)


def _validate_input_rows(rows: list[Any]) -> list[dict[str, Any]]:
    if not rows:
        raise JevTriageError("evidence_input_empty")
    if len(rows) > MAX_INPUT_ROWS:
        raise JevTriageError("evidence_row_limit_exceeded")
    if not all(isinstance(row, Mapping) for row in rows):
        raise JevTriageError("evidence_rows_must_be_objects")
    return [dict(row) for row in rows]


def _is_canonical_evidence_row(value: Mapping[str, Any]) -> bool:
    return all(key in value for key in ("evidence_id", "access_mode", "url"))


def prepare_public_evidence(
    rows: list[dict[str, Any]],
) -> tuple[list[PreparedEvidence], list[dict[str, Any]], int]:
    """Project only named public evidence fields; unknown metadata never leaves process."""

    prepared: list[PreparedEvidence] = []
    skipped: list[dict[str, Any]] = []
    public_rows = 0
    seen_ids: set[str] = set()
    for index, row in enumerate(rows, start=1):
        access_mode = str(row.get("access_mode") or "").strip()
        if access_mode not in PUBLIC_ACCESS_MODES or _has_private_source_marker(row):
            skipped.append({"row_index": index, "reason": "non_public_or_private_source"})
            continue
        public_rows += 1
        if len(prepared) >= MAX_EVIDENCE_ITEMS:
            skipped.append({"row_index": index, "reason": "evidence_item_limit"})
            continue
        evidence_id = str(row.get("evidence_id") or "").strip()
        if redact_text(evidence_id) != evidence_id:
            skipped.append({"row_index": index, "reason": "sensitive_evidence_id"})
            continue
        if not _SAFE_ID.fullmatch(evidence_id):
            skipped.append({"row_index": index, "reason": "invalid_evidence_id"})
            continue
        if evidence_id in seen_ids:
            skipped.append({"row_index": index, "reason": "duplicate_evidence_id"})
            continue
        url = safe_public_reference_url(str(row.get("url") or row.get("source_url") or ""))
        if not url:
            skipped.append({"row_index": index, "reason": "invalid_public_url"})
            continue
        raw_text = row.get("text") or row.get("text_excerpt") or ""
        if not isinstance(raw_text, str) or not raw_text.strip():
            skipped.append({"row_index": index, "reason": "missing_text"})
            continue
        if _contains_surrogate(raw_text):
            skipped.append({"row_index": index, "reason": "invalid_text_encoding"})
            continue
        text = redact_text(raw_text.strip())
        forwarded = text[:MAX_SOURCE_TEXT_CHARS]
        title = _safe_text(row.get("title") or url, MAX_TITLE_CHARS)
        source_kind = _safe_text(row.get("source_kind") or "", MAX_TITLE_CHARS)
        if title is None or source_kind is None:
            skipped.append({"row_index": index, "reason": "invalid_text_encoding"})
            continue
        prepared.append(
            PreparedEvidence(
                evidence_id=evidence_id,
                title=title,
                url=url,
                source_kind=source_kind,
                access_mode=access_mode,
                text=forwarded,
                source_text_chars=len(text),
                forwarded_text_chars=len(forwarded),
                text_truncated=len(text) > len(forwarded),
            )
        )
        seen_ids.add(evidence_id)
    if not prepared:
        raise JevTriageError("no_eligible_public_evidence")
    return prepared, skipped, public_rows


def _has_private_source_marker(row: Mapping[str, Any]) -> bool:
    for key in (
        "access_mode",
        "source_kind",
        "source_id",
        "connector",
        "source_class",
        "source_bridge",
        "bridge",
    ):
        value = str(row.get(key) or "").lower()
        normalized = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
        if any(marker in normalized.split("_") for marker in _PRIVATE_SOURCE_MARKERS):
            return True
        if any(marker in normalized for marker in ("agent_reach", "logged_in", "source_bridge")):
            return True
    return False


def safe_public_reference_url(value: str) -> str:
    """Strip URL parameters and reject clearly non-public references without fetching them."""

    if _contains_surrogate(value):
        return ""
    try:
        parsed = urlsplit(str(value or "").strip())
        if parsed.scheme.lower() not in {"http", "https"}:
            return ""
        if parsed.username is not None or parsed.password is not None:
            return ""
        host = str(parsed.hostname or "").lower().rstrip(".")
        if not host or host == "localhost" or host.endswith(_BLOCKED_HOST_SUFFIXES):
            return ""
        try:
            if not ipaddress.ip_address(host).is_global:
                return ""
        except ValueError:
            pass
        # Accessing .port validates malformed numeric ports.
        port = parsed.port
        netloc = host if port is None else f"{host}:{port}"
        cleaned = urlunsplit((parsed.scheme.lower(), netloc, parsed.path, "", ""))
    except ValueError:
        return ""
    return cleaned[:MAX_URL_CHARS]


def _safe_text(value: Any, limit: int) -> str | None:
    text = str(value or "").strip()
    if _contains_surrogate(text):
        return None
    return redact_text(text)[:limit]


def _contains_surrogate(value: str) -> bool:
    return any(0xD800 <= ord(character) <= 0xDFFF for character in value)


def resolve_api_key(
    *,
    prompt_key: bool = False,
    environ: Mapping[str, str] | None = None,
    keychain_lookup: Callable[[], str | None] | None = None,
    prompt: Callable[[str], str] | None = None,
) -> str | None:
    """Resolve a key without persisting or revealing it."""

    source = environ if environ is not None else os.environ
    key = _normalize_api_key(source.get("TYPESAFE_API_KEY"))
    if key:
        return key
    lookup = keychain_lookup or _macos_keychain_key
    key = _normalize_api_key(lookup())
    if key:
        return key
    if not prompt_key:
        return None
    if prompt is None:
        if not getattr(sys.stdin, "isatty", lambda: False)():
            return None
        try:
            import warnings

            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                prompted = getpass.getpass("TypeSafe API key (used only for this process): ")
        except (EOFError, KeyboardInterrupt, getpass.GetPassWarning):
            return None
        return _normalize_api_key(prompted)
    try:
        return _normalize_api_key(prompt("TypeSafe API key (used only for this process): "))
    except (EOFError, KeyboardInterrupt):
        return None


def _normalize_api_key(value: Any) -> str | None:
    raw = str(value or "")
    if not raw or len(raw) > 512 or any(character.isspace() or ord(character) < 32 for character in raw):
        return None
    return raw


def _macos_keychain_key() -> str | None:
    if sys.platform != "darwin":
        return None
    try:
        result = subprocess.run(
            [
                "/usr/bin/security",
                "find-generic-password",
                "-a",
                getpass.getuser(),
                "-s",
                KEYCHAIN_SERVICE,
                "-w",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def triage_public_evidence(
    *,
    topic: str,
    rows: list[dict[str, Any]],
    allow_jev: bool,
    prompt_key: bool = False,
    api_key: str | None = None,
    transport: Transport | None = None,
) -> dict[str, Any]:
    """Return typed advisory relevance judgments without touching canonical evidence."""

    started_at = utc_now()
    started_clock = time.perf_counter()
    events: list[dict[str, Any]] = [{"type": "triage_started", "at": started_at}]
    try:
        clean_topic = _validate_topic(topic)
        if not allow_jev:
            raise JevTriageError("jev_consent_required")
        prepared, skipped, public_rows = prepare_public_evidence(rows)
    except JevTriageError as exc:
        return _failure_result(
            code=exc.code,
            started_at=started_at,
            started_clock=started_clock,
            events=events,
            credential_configured=False,
        )

    key = _normalize_api_key(api_key) if api_key is not None else resolve_api_key(prompt_key=prompt_key)
    if not key:
        return _failure_result(
            code="credentials_unavailable",
            started_at=started_at,
            started_clock=started_clock,
            events=events,
            credential_configured=False,
            selection=_selection_summary(rows, prepared, skipped, public_rows),
        )
    request_payload = _build_request(topic=clean_topic, evidence=prepared)
    request_started_at = utc_now()
    events.append(
        {
            "type": "jev_request_started",
            "at": request_started_at,
            "question_count": len(prepared),
        }
    )
    request_clock = time.perf_counter()
    try:
        response = (transport or post_system_one)(request_payload, key, REQUEST_TIMEOUT_SECONDS)
        answers, model, usage = _parse_response(response, question_count=len(prepared))
    except JevServiceError as exc:
        elapsed = _elapsed_ms(request_clock)
        events.append(
            {
                "type": "jev_request_finished",
                "at": utc_now(),
                "status": "failed",
                "duration_ms": elapsed,
            }
        )
        return _failure_result(
            code=exc.code,
            started_at=started_at,
            started_clock=started_clock,
            events=events,
            credential_configured=True,
            selection=_selection_summary(rows, prepared, skipped, public_rows),
            request_ms=elapsed,
        )
    elapsed = _elapsed_ms(request_clock)
    events.append(
        {
            "type": "jev_request_finished",
            "at": utc_now(),
            "status": "complete",
            "duration_ms": elapsed,
            "question_count": len(prepared),
        }
    )
    events.append({"type": "triage_finished", "at": utc_now(), "status": "complete"})
    return {
        "schema_version": RESULT_SCHEMA,
        "status": "complete",
        "advisory_only": True,
        "disclaimer": (
            "Jev judged topical relevance only. No source was fetched, verified, added, "
            "removed, or excluded."
        ),
        "model": model,
        "credential_configured": True,
        "selection": _selection_summary(rows, prepared, skipped, public_rows),
        "judgments": [
            evidence.result_value(noul=answers[f"item_{index}"])
            for index, evidence in enumerate(prepared, start=1)
        ],
        "usage": usage,
        "timing": {
            "request_ms": elapsed,
            "total_ms": _elapsed_ms(started_clock),
        },
        "events": events,
    }


def failed_triage_result(code: str) -> dict[str, Any]:
    """Render a bounded local CLI failure without loading or sending evidence."""

    started_at = utc_now()
    started_clock = time.perf_counter()
    return _failure_result(
        code=code,
        started_at=started_at,
        started_clock=started_clock,
        events=[{"type": "triage_started", "at": started_at}],
        credential_configured=False,
    )


def _validate_topic(topic: str) -> str:
    raw = str(topic or "").strip()
    if _contains_surrogate(raw):
        raise JevTriageError("invalid_text_encoding")
    clean = redact_text(raw)
    if not clean:
        raise JevTriageError("topic_required")
    if len(clean) > MAX_TOPIC_CHARS:
        raise JevTriageError("topic_too_long")
    return clean


def _build_request(*, topic: str, evidence: list[PreparedEvidence]) -> dict[str, Any]:
    questions = {
        f"item_{index}": {
            "type": "noul",
            "instructions": (
                f"Is evidence item at `evidence[{index - 1}]` directly relevant to `topic`? "
                "Judge topical relevance only. Do not assess factual truth, source authenticity, "
                "or whether the evidence should be included or excluded."
            ),
            "criteria": {
                "true": "The supplied public evidence directly addresses the research topic.",
                "false": "The supplied public evidence is not directly about the research topic.",
            },
        }
        for index in range(1, len(evidence) + 1)
    }
    return {
        "state": {"topic": topic, "evidence": [item.state_value() for item in evidence]},
        "model": JEV_MODEL,
        "questions": questions,
    }


def post_system_one(payload: dict[str, Any], api_key: str, timeout_seconds: float) -> Mapping[str, Any]:
    """Call the documented System One endpoint, without surfacing response bodies on failure."""

    try:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = Request(
            TYPESAFE_ENDPOINT,
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with _NO_REDIRECT_OPENER.open(request, timeout=timeout_seconds) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        raise JevServiceError(_http_error_code(exc.code)) from exc
    except (URLError, OSError, TimeoutError, ValueError, UnicodeEncodeError):
        raise JevServiceError("network_unavailable") from None
    if len(raw) > MAX_RESPONSE_BYTES:
        raise JevServiceError("response_too_large")
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise JevServiceError("invalid_response") from None
    if not isinstance(parsed, Mapping):
        raise JevServiceError("invalid_response")
    return parsed


def _http_error_code(status: int) -> str:
    if 300 <= status < 400:
        return "redirect_blocked"
    if status == 401:
        return "credentials_rejected"
    if status == 429:
        return "rate_limited"
    if status == 529:
        return "provider_overloaded"
    return "provider_request_failed"


def _parse_response(
    response: Mapping[str, Any], *, question_count: int
) -> tuple[dict[str, float], str, dict[str, int]]:
    model = redact_text(str(response.get("model") or ""))
    answers_raw = response.get("answers")
    usage_raw = response.get("usage")
    if not _SAFE_MODEL.fullmatch(model) or not isinstance(answers_raw, Mapping):
        raise JevServiceError("invalid_response")
    answers: dict[str, float] = {}
    for index in range(1, question_count + 1):
        key = f"item_{index}"
        answer = answers_raw.get(key)
        if not isinstance(answer, Mapping) or answer.get("type") != "noul":
            raise JevServiceError("invalid_response")
        value = answer.get("noul")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise JevServiceError("invalid_response")
        numeric = float(value)
        if not math.isfinite(numeric) or not 0.0 <= numeric <= 1.0:
            raise JevServiceError("invalid_response")
        answers[key] = numeric
    if not isinstance(usage_raw, Mapping):
        raise JevServiceError("invalid_response")
    usage: dict[str, int] = {}
    for name in ("input_tokens", "output_tokens"):
        value = usage_raw.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise JevServiceError("invalid_response")
        usage[name] = value
    return answers, model, usage


def _selection_summary(
    rows: list[dict[str, Any]],
    prepared: list[PreparedEvidence],
    skipped: list[dict[str, Any]],
    public_rows: int,
) -> dict[str, Any]:
    return {
        "input_rows": len(rows),
        "public_access_mode_rows": public_rows,
        "selected_rows": len(prepared),
        "not_selected_rows": len(rows) - len(prepared),
        "skipped": skipped,
    }


def _failure_result(
    *,
    code: str,
    started_at: str,
    started_clock: float,
    events: list[dict[str, Any]],
    credential_configured: bool,
    selection: dict[str, Any] | None = None,
    request_ms: float | None = None,
) -> dict[str, Any]:
    events.append({"type": "triage_finished", "at": utc_now(), "status": "failed"})
    timing: dict[str, float] = {"total_ms": _elapsed_ms(started_clock)}
    if request_ms is not None:
        timing["request_ms"] = request_ms
    return {
        "schema_version": RESULT_SCHEMA,
        "status": "failed",
        "error_code": code,
        "advisory_only": True,
        "credential_configured": credential_configured,
        "selection": selection or {
            "input_rows": 0,
            "public_access_mode_rows": 0,
            "selected_rows": 0,
            "not_selected_rows": 0,
            "skipped": [],
        },
        "usage": None,
        "timing": timing,
        "events": events,
    }


def _elapsed_ms(started_clock: float) -> float:
    return round((time.perf_counter() - started_clock) * 1000, 3)
