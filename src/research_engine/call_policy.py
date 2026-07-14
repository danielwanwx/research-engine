"""Fail-closed policies for external and paid research calls."""

from __future__ import annotations

import os
from typing import Any, Mapping


def paid_discovery_decision(
    source: Mapping[str, Any],
    *,
    transport_injected: bool,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    env = os.environ if environ is None else environ
    budget = _non_negative_int(source.get("paid_call_budget"))
    base = {"paid_calls_allowed": budget}
    if transport_injected:
        return {**base, "allowed": True, "stop_reason": "injected_transport"}
    if env.get("PYTEST_CURRENT_TEST"):
        return {**base, "allowed": False, "stop_reason": "blocked_in_test"}
    if _truthy(env.get("RESEARCH_ENGINE_EXTERNAL_CALLS_DISABLED")):
        return {**base, "allowed": False, "stop_reason": "external_calls_disabled"}
    if source.get("paid_call_approved") is not True:
        return {**base, "allowed": False, "stop_reason": "paid_calls_not_approved"}
    if budget < 1:
        return {**base, "allowed": False, "stop_reason": "paid_call_budget_exhausted"}
    return {**base, "allowed": True, "stop_reason": "within_budget"}


def external_discovery_decision(
    source: Mapping[str, Any],
    *,
    transport_injected: bool,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    env = os.environ if environ is None else environ
    if transport_injected:
        return {"allowed": True, "stop_reason": "injected_transport"}
    if env.get("PYTEST_CURRENT_TEST"):
        return {"allowed": False, "stop_reason": "blocked_in_test"}
    if _truthy(env.get("RESEARCH_ENGINE_EXTERNAL_CALLS_DISABLED")):
        return {"allowed": False, "stop_reason": "external_calls_disabled"}
    if source.get("external_discovery_approved") is not True:
        return {"allowed": False, "stop_reason": "external_discovery_not_approved"}
    return {"allowed": True, "stop_reason": "approved"}


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _non_negative_int(value: object) -> int:
    try:
        return max(0, int(str(value or "0").strip()))
    except ValueError:
        return 0
