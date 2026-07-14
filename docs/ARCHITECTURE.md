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

## Milestone 2 additions

### Match State Engine (`match/engine.py`)
`MatchStateEngine` subscribes to `GSIStateUpdated` and, per payload: runs the
detector, rebuilds the immutable `LiveMatch` model (`match/model.py`) carrying
round *history* forward, accumulates statistics, persists, and republishes a
`MatchModelUpdated` plus each detected event. It is the single source of truth.
It runs on the GSI network thread, guards shared state with a lock, and only
ever hands *immutable* `LiveMatch` snapshots to readers — so the UI never sees a
half-updated model. Momentum, round importance and series importance are pure
functions of the model, making them trivially testable.

### Event detection (`detection/`)
The `EventDetector` is a **stateful diff** over consecutive payloads. GSI gives
cumulative kills and current health but never links killer→victim, so deaths are
detected reliably (health→0), kills are credited to whoever's cumulative count
rose, and the two are paired only when a tick is unambiguous; uncertain
inferences carry a sub-1.0 `confidence`. Detected events subclass the core
`Event`, so they ride the same bus and route to any subscriber (UI now; the
Commentary Director in M5).

### Statistics (`statistics/`) and persistence (`persistence/`)
The `StatisticsEngine` reads authoritative cumulative fields from the snapshot
and folds event/round-derived numbers (opening kills, trades, clutches, damage,
multi-kills) on top. Persistence uses stdlib `sqlite3` behind a `MatchRepository`
so all SQL lives in one place, writes are parameterised, and a PostgreSQL
implementation can replace it later without touching call sites. The connection
is shared across threads and serialised with a lock; WAL mode keeps writes from
blocking reads during long broadcasts.

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
│   ├── state.py       # MatchStateStore (lightweight latest snapshot)
│   ├── model.py       # Module 8: LiveMatch model + momentum/importance
│   ├── engine.py      # Module 8: MatchStateEngine (single source of truth)
│   └── events.py      # MatchModelUpdated bus event
├── detection/
│   ├── events.py      # Module 9: detected MatchEvent types
│   └── detectors.py   # Module 9: stateful GSI diff detector
├── statistics/
│   ├── models.py      # Module 17: PlayerStats / MatchStatistics
│   └── engine.py      # Module 17: StatisticsEngine
├── persistence/
│   ├── database.py    # SQLite connection + schema (migration-ready)
│   └── repository.py  # MatchRepository (all SQL in one place)
└── ui/
    ├── main_window.py # Module 1: PySide6 shell + navigation
    ├── qt_event_bridge.py
    └── views/         # dashboard, GSI, match engine, statistics, settings, …
```

## Threading model
- **Qt thread:** owns all widgets. Never touched by network code directly.
- **GSI server thread:** runs uvicorn; parses payloads; publishes events.
- **Bridge:** `QtEventBridge` subscribes to the bus and re-emits a Qt signal so
  UI updates always happen on the Qt thread.

## Testing
`pytest` drives everything. Domain modules (config, gsi, match, detection,
statistics, persistence) have no Qt or network dependency and run headless in
CI. The FastAPI endpoint is tested with Starlette's `TestClient`; persistence is
tested against a temp-file SQLite database; the Match Engine is tested end-to-end
by publishing GSI payloads on the bus and asserting on the model, events, stats
and stored rows.
