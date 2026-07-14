# AI Esports Caster — Architecture

## Overview

AI Esports Caster is a modular Windows desktop application that autonomously
casts Counter-Strike 2 matches. The system is organised as a set of independent
modules that communicate through **clean interfaces** and an internal
**event bus**. The composition root (`ai_caster/app.py`) wires modules together
using dependency injection so that any module can be unit-tested in isolation.

```
                         ┌────────────────────────────┐
                         │        Desktop UI (M1)      │  PySide6
                         │  (subscribes to events;     │
                         │   never depended upon)      │
                         └──────────────┬─────────────┘
                                        │ reads
        publishes events                ▼
  ┌──────────────┐   events    ┌────────────────────┐
  │ GSI Receiver │────────────▶│      Event Bus      │◀── (future modules:
  │    (M1)      │             │  thread-safe pub/sub │     vision, director,
  └──────┬───────┘             └─────────┬───────────┘     voice, ...)
         │ updates                       │
         ▼                               ▼
  ┌──────────────┐              ┌───────────────────┐
  │ Match State  │              │ Logging & Diag.   │
  │ Store (M1→M2)│              │      (M1)          │
  └──────────────┘              └───────────────────┘
```

## Key design decisions (Milestone 1)

### 1. `src/` layout + installable package
The application ships as an installable Python package (`ai_caster`) using a
`src/` layout. This prevents accidental imports of the working tree, forces the
test suite to exercise the *installed* package, and matches production packaging
(PyInstaller/Docker later).

### 2. Event bus for decoupling
Modules never import each other's concrete classes to communicate. Instead they
publish/subscribe to typed events on a thread-safe `EventBus`. This is what lets
the GSI receiver (running on a network thread) hand data to the UI (running on
the Qt thread) without either knowing about the other. Handlers are dispatched
synchronously on the publisher's thread; the UI adapter marshals events onto the
Qt event loop via a Qt signal, which is the correct pattern for cross-thread UI
updates.

### 3. Configuration as typed models
All settings are defined as **pydantic** models (`ai_caster/config/models.py`),
giving validation, defaults and self-documentation for free. The
`SettingsManager` persists them as human-readable JSON in the OS-appropriate
per-user config directory and validates on load, falling back to defaults for
missing/corrupt values rather than crashing.

### 4. Framework-agnostic GSI core
CS2 Game State Integration delivers data by HTTP POST. We separate the
**transport** (a FastAPI app) from the **domain** (`GSIReceiver`): the receiver
exposes `handle_payload(dict) -> GameState` and is fully unit-testable without a
running socket. The FastAPI layer is a thin adapter that validates the auth
token and calls the receiver. The HTTP server runs on a background thread so it
never blocks the Qt UI thread.

### 5. Priority of truth (enforced from the start)
The eventual Match State Engine ranks data sources: **Server events > GSI >
Vision > Inference.** In Milestone 1 only GSI exists, but the `MatchStateStore`
already records the *source* and *confidence* of every field so later fusion
logic can honour this ordering without a rewrite.

## Package layout

```
src/ai_caster/
├── app.py             # composition root / dependency injection
├── __main__.py        # `python -m ai_caster`
├── core/
│   ├── logging.py     # Module 20: structured, rotating, timestamped logging
│   ├── events.py      # EventBus + event dataclasses
│   ├── interfaces.py  # abstract base classes / protocols
│   └── paths.py       # OS-appropriate config/log/data directories
├── config/
│   ├── models.py      # Module 2: pydantic settings models
│   └── manager.py     # SettingsManager (load/save/observe)
├── gsi/
│   ├── models.py      # typed CS2 GSI payload models
│   ├── receiver.py    # Module 5: framework-agnostic ingest + publish
│   ├── server.py      # FastAPI transport running on a background thread
│   └── cfg.py         # CS2 GSI .cfg generator
├── match/
│   └── state.py       # MatchStateStore (foundation for M2 Match Engine)
└── ui/
    ├── main_window.py # Module 1: PySide6 shell + navigation
    ├── qt_event_bridge.py
    └── views/         # dashboard, live GSI monitor, settings, placeholders
```

## Threading model
- **Qt thread:** owns all widgets. Never touched by network code directly.
- **GSI server thread:** runs uvicorn; parses payloads; publishes events.
- **Bridge:** `QtEventBridge` subscribes to the bus and re-emits a Qt signal so
  UI updates always happen on the Qt thread.

## Testing
`pytest` drives everything. Domain modules (config, gsi, events, match) have no
Qt or network dependency and run headless in CI. The FastAPI endpoint is tested
with Starlette's `TestClient`.
