"""Shared abstract interfaces.

These protocols define the contracts feature modules implement so the
composition root can wire concrete implementations via dependency injection and
tests can substitute fakes. Kept deliberately small in Milestone 1; each future
milestone adds the interface for its module here.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Service(Protocol):
    """A long-lived component with an explicit lifecycle.

    Every background module (GSI server, future video capture, voice engine,
    ...) implements this so the application can start and stop them uniformly.
    Implementations must be idempotent: calling :meth:`start`/:meth:`stop`
    twice is safe.
    """

    def start(self) -> None:
        """Begin operating (bind sockets, spawn threads, ...)."""
        ...

    def stop(self) -> None:
        """Stop operating and release all resources."""
        ...

    @property
    def is_running(self) -> bool:
        """Whether the service is currently active."""
        ...


@runtime_checkable
class MatchStateProvider(Protocol):
    """Something that can supply the current authoritative match snapshot.

    Milestone 1 implements this over GSI only; the Match State Engine (M2) will
    provide the fused version. UI and future modules depend on this interface,
    never on a concrete store.
    """

    def snapshot(self) -> Any:
        """Return the latest immutable match snapshot (or ``None`` if none yet)."""
        ...
