"""Checks for capabilities that are intentionally kept out of the core install."""

from __future__ import annotations

import importlib.util


class MissingOptionalDependency(RuntimeError):
    """Raised when a user explicitly requests an optional capability."""


def require_report_dependency() -> None:
    """Require ReportLab only for the explicit full-report path.

    Keeping this check at the boundary makes summary runs usable in a minimal
    environment and gives callers an actionable error before a run directory
    is reserved.
    """

    try:
        available = importlib.util.find_spec("reportlab") is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        available = False
    if available:
        return
    raise MissingOptionalDependency(
        "full report mode requires the optional 'report' dependency; "
        "install it with `pip install research-engine[report]`"
    )
