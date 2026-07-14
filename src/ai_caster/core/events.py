"""The internal event bus and the event types published across module
boundaries.

Every module communicates through this bus rather than importing each other's
concrete classes. This is what lets the GSI receiver (network thread) hand data
to the UI (Qt thread) without either side knowing about the other.

Threading contract
-------------------
:meth:`EventBus.publish` invokes subscribers **synchronously on the calling
thread**. Subscribers must therefore be quick and thread-safe. UI code must not
touch widgets from a handler directly — the :class:`~ai_caster.ui.qt_event_bridge.QtEventBridge`
marshals events onto the Qt event loop. A misbehaving subscriber cannot break
the publisher: handler exceptions are caught and logged.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, TypeVar

from ai_caster.core.logging import get_logger

_log = get_logger("core.events")


def _utcnow() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- #
# Event types
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Event:
    """Base class for all events. Carries a UTC timestamp for the logs."""

    timestamp: datetime = field(default_factory=_utcnow, kw_only=True)


@dataclass(frozen=True)
class GSIStateUpdated(Event):
    """A new CS2 GSI payload has been received, validated and parsed.

    ``game_state`` is the freshly parsed :class:`~ai_caster.gsi.models.GameState`.
    Typed as ``Any`` here to keep :mod:`core` free of feature-module imports and
    avoid a circular dependency.
    """

    game_state: Any = None


@dataclass(frozen=True)
class GSIConnectionChanged(Event):
    """The GSI receiver's perceived connection state changed.

    ``connected`` is ``True`` when payloads are arriving, ``False`` when the feed
    has gone quiet past the staleness threshold.
    """

    connected: bool = False
    detail: str = ""


@dataclass(frozen=True)
class SettingsChanged(Event):
    """Persisted settings were reloaded or modified. ``section`` names the top
    level settings group that changed, or ``"*"`` for a full reload."""

    section: str = "*"


E = TypeVar("E", bound=Event)
Handler = Callable[[Event], None]


# --------------------------------------------------------------------------- #
# Bus
# --------------------------------------------------------------------------- #
class EventBus:
    """A minimal, thread-safe, type-routed publish/subscribe bus.

    Subscriptions are keyed by event *class*. Subscribing to :class:`Event`
    receives everything.
    """

    def __init__(self) -> None:
        self._subscribers: dict[type[Event], list[Handler]] = defaultdict(list)
        self._lock = threading.RLock()

    def subscribe(self, event_type: type[E], handler: Callable[[E], None]) -> Callable[[], None]:
        """Register ``handler`` for ``event_type``.

        Returns an unsubscribe callable so callers don't need to retain the
        handler reference themselves.
        """
        with self._lock:
            self._subscribers[event_type].append(handler)  # type: ignore[arg-type]
        _log.debug(
            "Subscribed %s to %s",
            getattr(handler, "__qualname__", handler),
            event_type.__name__,
        )

        def _unsubscribe() -> None:
            self.unsubscribe(event_type, handler)

        return _unsubscribe

    def unsubscribe(self, event_type: type[E], handler: Callable[[E], None]) -> None:
        """Remove a previously registered handler. Silently ignores unknowns."""
        with self._lock:
            handlers = self._subscribers.get(event_type)
            if handlers and handler in handlers:  # type: ignore[operator]
                handlers.remove(handler)  # type: ignore[arg-type]

    def publish(self, event: Event) -> None:
        """Dispatch ``event`` to every handler registered for its exact type and
        for any base type in its MRO (so ``Event`` subscribers get everything).

        Handlers run synchronously on the caller's thread. Exceptions are caught
        and logged so one bad subscriber can't take down the publisher.
        """
        # Snapshot handlers under the lock, then invoke outside it so a handler
        # may (un)subscribe without deadlocking.
        with self._lock:
            handlers: list[Handler] = []
            for event_type in type(event).__mro__:
                if event_type in self._subscribers:
                    handlers.extend(self._subscribers[event_type])

        for handler in handlers:
            try:
                handler(event)
            except Exception:  # noqa: BLE001 - isolate subscriber failures
                _log.exception(
                    "Event handler %s failed for %s",
                    getattr(handler, "__qualname__", handler),
                    type(event).__name__,
                )

    def clear(self) -> None:
        """Remove all subscriptions. Primarily for teardown in tests."""
        with self._lock:
            self._subscribers.clear()
