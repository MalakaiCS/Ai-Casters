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
import urllib.error
import urllib.request
from typing import Any


class HttpError(RuntimeError):
    """Any failure talking to a backend service (network, HTTP or decode)."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


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

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:  # pragma: no cover - needs a live server
        raise HttpError(f"{method} {url} failed: HTTP {exc.code}", status=exc.code) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:  # pragma: no cover - network
        raise HttpError(f"{method} {url} failed: {exc}") from exc

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
