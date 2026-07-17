"""A tiny stdlib JSON-over-HTTP helper.

The account, licensing, updater and sync clients each talk to a backend service.
Rather than pull in a runtime HTTP dependency, they share this thin wrapper over
:mod:`urllib.request`, which keeps the package lean and means the *offline*
default backends (used everywhere by default and in every test) need nothing at
all. Network and protocol failures are normalised to :class:`HttpError` so
callers can degrade gracefully instead of leaking assorted urllib exceptions.
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from functools import lru_cache
from typing import Any


class HttpError(RuntimeError):
    """Any failure talking to a backend service (network, HTTP or decode)."""

    def __init__(self, message: str, *, status: int | None = None, reason: str = "") -> None:
        super().__init__(message)
        self.status = status
        # Underlying transport reason for a connection-level failure (TLS,
        # DNS, timeout, refused). Empty for HTTP-status errors.
        self.reason = reason


@lru_cache(maxsize=1)
def _ssl_context() -> ssl.SSLContext:
    """A verifying TLS context that works in a frozen (PyInstaller) build.

    A packaged app may not have access to the OS trust store, which makes every
    HTTPS call fail with a certificate error that surfaces as a generic "network"
    problem. Prefer certifi's bundled CA store (PyInstaller collects it) and fall
    back to the system default when certifi isn't available.
    """
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001 - any failure falls back to the default trust store
        return ssl.create_default_context()


def _request(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None,
    headers: dict[str, str] | None,
    timeout: float,
) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Accept", "application/json")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)

    context = _ssl_context() if url.lower().startswith("https") else None
    try:
        with urllib.request.urlopen(  # noqa: S310
            request, timeout=timeout, context=context
        ) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:  # pragma: no cover - needs a live server
        raise HttpError(f"{method} {url} failed: HTTP {exc.code}", status=exc.code) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:  # pragma: no cover - network
        reason = getattr(exc, "reason", None)
        reason_text = str(reason) if reason is not None else str(exc)
        raise HttpError(f"{method} {url} failed: {reason_text}", reason=reason_text) from exc

    if not body:
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:  # pragma: no cover - malformed server response
        raise HttpError(f"{method} {url} returned invalid JSON") from exc


def get_json(url: str, *, headers: dict[str, str] | None = None, timeout: float = 8.0) -> Any:
    """GET ``url`` and decode the JSON body, raising :class:`HttpError` on failure."""
    return _request("GET", url, payload=None, headers=headers, timeout=timeout)


def post_json(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 8.0,
) -> Any:
    """POST ``payload`` as JSON and decode the JSON response."""
    return _request("POST", url, payload=payload, headers=headers, timeout=timeout)


def delete_json(url: str, *, headers: dict[str, str] | None = None, timeout: float = 8.0) -> Any:
    """DELETE ``url`` and decode any JSON body (empty response yields ``{}``)."""
    return _request("DELETE", url, payload=None, headers=headers, timeout=timeout)
