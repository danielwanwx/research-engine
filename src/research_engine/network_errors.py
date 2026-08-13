"""Safe classification for transient external-network failures."""

from __future__ import annotations

import socket
import ssl
from urllib.error import URLError


class TransientNetworkError(RuntimeError):
    """Retryable network failure carrying only a safe category."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def transient_network_reason(exc: BaseException) -> str:
    """Return a stable safe reason, or an empty string for non-network failures."""

    if isinstance(exc, TransientNetworkError):
        return exc.reason
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return "network_timeout"
    if isinstance(exc, ssl.SSLError):
        return "tls_failure"
    if isinstance(exc, socket.gaierror):
        return "dns_resolution_failed"
    if isinstance(exc, URLError):
        nested = exc.reason
        if isinstance(nested, socket.gaierror):
            return "dns_resolution_failed"
        if isinstance(nested, (TimeoutError, socket.timeout)):
            return "network_timeout"
        if isinstance(nested, ssl.SSLError):
            return "tls_failure"
        return "network_unavailable"
    if isinstance(exc, ValueError) and "host could not be resolved" in str(exc).lower():
        return "dns_resolution_failed"
    return ""


def raise_if_transient_network_error(exc: BaseException) -> None:
    reason = transient_network_reason(exc)
    if reason:
        raise TransientNetworkError(reason) from exc
