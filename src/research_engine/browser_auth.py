"""Consent and read-only policy primitives for authenticated browser collection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from research_engine.security import sanitize_for_artifact, side_effect_terms


DEFAULT_BROWSER_AUTH_ROOT = Path.home() / ".research-engine" / "browser-auth"
CONSENT_FILE = "consents.json"
SAFE_BROWSER_ACTIONS = frozenset({"expand_text", "next_page", "open_result", "scroll"})
SAFE_HTTP_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
RECIPE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_origin(value: str) -> str:
    """Return a strict HTTP(S) origin without path, query, or credentials."""
    parsed = urlsplit(str(value).strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("origin must be an absolute http(s) URL")
    if parsed.username or parsed.password:
        raise ValueError("origin must not contain credentials")
    host = parsed.hostname.lower().rstrip(".")
    if ":" in host:
        host = f"[{host}]"
    port = parsed.port
    if (parsed.scheme.lower(), port) in {("http", 80), ("https", 443)}:
        port = None
    netloc = f"{host}:{port}" if port else host
    return urlunsplit((parsed.scheme.lower(), netloc, "", "", ""))


def public_url(value: str) -> str:
    """Strip credentials, query, and fragment before a URL enters an artifact."""
    parsed = urlsplit(str(value).strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return ""
    try:
        origin = normalize_origin(value)
    except ValueError:
        return ""
    return f"{origin}{parsed.path or '/'}"


@dataclass(frozen=True)
class AuthChallenge:
    challenge_id: str
    recipe_id: str
    recipe_version: int
    origin: str
    requested_url: str
    reason: str
    status: str
    human_action_required: bool
    consent_required: bool
    created_at: str

    def as_dict(self) -> dict[str, Any]:
        return sanitize_for_artifact(asdict(self))


def create_auth_challenge(
    *,
    recipe_id: str,
    recipe_version: int,
    url: str,
    reason: str,
    status: str = "pending",
    human_action_required: bool = True,
    consent_required: bool = True,
) -> AuthChallenge:
    origin = normalize_origin(url)
    safe_url = public_url(url)
    stable = f"{recipe_id}\0{recipe_version}\0{origin}\0{safe_url}\0{reason}"
    challenge_id = hashlib.sha256(stable.encode("utf-8")).hexdigest()[:20]
    return AuthChallenge(
        challenge_id=challenge_id,
        recipe_id=recipe_id,
        recipe_version=int(recipe_version),
        origin=origin,
        requested_url=safe_url,
        reason=str(reason),
        status=str(status),
        human_action_required=bool(human_action_required),
        consent_required=bool(consent_required),
        created_at=utc_now(),
    )


class ConsentStore:
    """Recipe-versioned, exact-origin consent stored outside run artifacts."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or DEFAULT_BROWSER_AUTH_ROOT).expanduser()
        self.path = self.root / CONSENT_FILE

    def list_grants(self) -> list[dict[str, Any]]:
        payload = self._read()
        grants = payload.get("grants") or []
        return [dict(item) for item in grants if isinstance(item, dict)]

    def has_consent(self, *, recipe_id: str, recipe_version: int, origin: str) -> bool:
        expected_origin = normalize_origin(origin)
        return any(
            str(grant.get("recipe_id") or "") == recipe_id
            and int(grant.get("recipe_version") or 0) == int(recipe_version)
            and str(grant.get("origin") or "") == expected_origin
            for grant in self.list_grants()
        )

    def grant(self, *, recipe_id: str, recipe_version: int, origin: str) -> dict[str, Any]:
        normalized = normalize_origin(origin)
        grants = [
            grant
            for grant in self.list_grants()
            if not (
                str(grant.get("recipe_id") or "") == recipe_id
                and str(grant.get("origin") or "") == normalized
            )
        ]
        record = {
            "recipe_id": str(recipe_id),
            "recipe_version": int(recipe_version),
            "origin": normalized,
            "granted_at": utc_now(),
        }
        grants.append(record)
        self._write({"schema_version": "browser_consents.v1", "grants": grants})
        return dict(record)

    def revoke(self, *, recipe_id: str, origin: str | None = None) -> int:
        normalized = normalize_origin(origin) if origin else None
        current = self.list_grants()
        retained = [
            grant
            for grant in current
            if not (
                str(grant.get("recipe_id") or "") == recipe_id
                and (normalized is None or str(grant.get("origin") or "") == normalized)
            )
        ]
        removed = len(current) - len(retained)
        if removed:
            self._write({"schema_version": "browser_consents.v1", "grants": retained})
        return removed

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write(self, payload: dict[str, Any]) -> None:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        handle = tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self.root,
            prefix=".consents-",
            delete=False,
        )
        temporary = Path(handle.name)
        try:
            with handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
        finally:
            if temporary.exists():
                temporary.unlink()


def clear_browser_profile(
    recipe_id: str,
    *,
    root: Path | None = None,
    origin: str = "",
) -> bool:
    """Delete exactly one dedicated site profile after validating its identifier."""
    normalized = str(recipe_id).strip().lower()
    if not RECIPE_ID_RE.fullmatch(normalized):
        raise ValueError("invalid recipe id")
    auth_root = Path(root or DEFAULT_BROWSER_AUTH_ROOT).expanduser()
    profiles_root = auth_root / "profiles"
    target = profiles_root / browser_profile_key(normalized, origin=origin)
    if target.is_symlink():
        target.unlink()
        return True
    if not target.exists():
        return False
    if target.parent.resolve(strict=False) != profiles_root.resolve(strict=False):
        raise ValueError("profile target escaped the browser auth root")
    shutil.rmtree(target)
    return True


def browser_profile_key(recipe_id: str, *, origin: str = "") -> str:
    normalized = str(recipe_id).strip().lower()
    if not RECIPE_ID_RE.fullmatch(normalized):
        raise ValueError("invalid recipe id")
    if normalized != "generic":
        return normalized
    if not origin:
        raise ValueError("generic browser profiles require an exact origin")
    digest = hashlib.sha256(normalize_origin(origin).encode("utf-8")).hexdigest()[:12]
    return f"generic-{digest}"


@dataclass(frozen=True)
class CapturePolicy:
    allowed_origins: tuple[str, ...]
    read_only_post_operations: tuple[str, ...] = ()
    max_results: int = 10
    max_pages: int = 10
    max_scrolls: int = 10
    timeout_seconds: int = 60

    @classmethod
    def for_request(
        cls,
        *,
        origins: tuple[str, ...],
        max_results: int,
        depth: str,
        read_only_post_operations: tuple[str, ...] = (),
    ) -> "CapturePolicy":
        bounded = max(1, int(max_results))
        timeout = {"quick": 60, "deep": 180, "audit": 300}.get(str(depth), 60)
        return cls(
            allowed_origins=tuple(normalize_origin(origin) for origin in origins),
            read_only_post_operations=tuple(read_only_post_operations),
            max_results=bounded,
            max_pages=bounded,
            max_scrolls=max(3, bounded),
            timeout_seconds=timeout,
        )

    def check_action(self, action: str) -> tuple[bool, str]:
        normalized = str(action).strip().lower()
        if side_effect_terms([normalized]):
            return False, "mutation_action_denied"
        if normalized not in SAFE_BROWSER_ACTIONS:
            return False, "unknown_action_denied"
        return True, "allowed"

    def check_request(
        self,
        *,
        method: str,
        url: str,
        operation: str = "",
    ) -> tuple[bool, str]:
        try:
            origin = normalize_origin(url)
        except ValueError:
            return False, "invalid_url_denied"
        if origin not in self.allowed_origins:
            return False, "cross_origin_denied"
        normalized_method = str(method).upper()
        if normalized_method in SAFE_HTTP_METHODS:
            return True, "allowed"
        if normalized_method == "POST" and operation in self.read_only_post_operations:
            return True, "allowed_read_only_operation"
        return False, "write_request_denied"
