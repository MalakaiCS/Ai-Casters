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

## Milestone 3 additions

### Video capture (`capture/`)
Capture is built around a `FrameSource` abstraction so the pipeline is identical
regardless of where pixels originate. The **synthetic** source is the default,
which is what lets the whole application (and CI) run with no display or capture
hardware; real backends (monitor via mss, window via mss + pygetwindow, capture
card via OpenCV) live in `capture/backends/` and **lazy-import** their native
dependency inside `open()`, so importing the package is cheap and a missing
capture library only fails — loudly and clearly — when you actually start that
source.

The `CapturePipeline` runs a **paced loop on its own thread**: grab → GPU-upload
seam → ring buffer → per-frame callbacks → stats. Individual frames are handed to
registered callbacks (the vision system in M4) rather than published on the bus —
at 60 fps the bus would be the wrong tool — while only coarse status and ~1 Hz
stats go on the bus for the UI. The pacing math (`FrameClock`) is separated from
the sleeping so it is unit-tested deterministically, and `capture_once()` runs a
single iteration so the whole pipeline can be driven without real timing.

"GPU acceleration where available" is an honest, injectable seam: every frame
passes through a `FrameUploader` (a CPU no-op today) and startup probes for a
real accelerator so diagnostics report the truth. M4 plugs a CUDA uploader in
here without the pipeline changing.

## Milestone 4 additions

### Computer vision (`vision/`)
Vision consumes captured frames (registered as a capture callback), throttles to
a configured analysis rate, downscales, and runs a set of **detectors** that
share one interface: `detect(image, frame_index) -> list[VisionObservation]`.
Because a detector is a pure function of pixels, every one is unit-tested with a
hand-crafted NumPy array.

Two families implement that interface. **Analytic** detectors use classical
colour statistics (`vision/color.py`) over resolution-independent regions of
interest (`vision/roi.py`) — flash, smoke, fire, kill-feed/bomb-timer activity,
HUD presence and a heuristic scene classifier. They need no model, so they are
always available and honest about confidence (the scene classifier caps its
confidence and never guesses *replay* — that authoritative signal comes from the
external replay integration in M5). The **model-backed** `OnnxObjectDetector`
(behind the `[vision]` extra) loads *user-supplied* weights via onnxruntime; no
weights ship with the project, and a missing runtime/model degrades gracefully to
the analytic detectors.

Per-frame observations are folded into an immutable `VisionState` and published
at the throttled rate (never per raw frame). The **fusion** primitive
(`vision/fusion.py`) encodes the project rule — Server > GSI > Vision >
Inference — as a tiny tested function: `fuse_effect` lets a confirmed GSI reading
always win and consults vision only when GSI is silent. The Match Engine attaches
the latest `VisionState` to `LiveMatch.visual` as an **annotation**; the
GSI-authoritative gameplay fields are never derived from vision, so uncertain
vision can never override confirmed match data.

## Milestone 5 additions

### Commentary Director (`director/`) and Replay (`replay/`)
The **Commentary Director** is the broadcast-flow brain: it subscribes to match
events, the live model, vision and replay state and emits `CommentaryDirective`
decisions — which role should speak (play-by-play vs. analyst), at what priority
and excitement, whether a directive interrupts current speech, and when to stay
silent or hand off. It **never generates prose**; the M6 AIs do that. The
decision surface is split into pure policy functions (`director/policy.py`:
speaker/priority/excitement/context/`is_live_broadcast`) and a thin stateful
`CommentaryDirector` that applies them with an injectable clock, so interruption
and rate-limit behaviour is deterministic under test. A speaking-time budget per
priority governs interruption (a strictly higher priority cuts in) and yielding
(equal/lower priority stays silent), with the configured `min_speech_gap_ms` as a
floor.

**Replay integration** mirrors GSI: a framework-agnostic `ReplayReceiver`
(`handle_event`) maintains the authoritative `ReplayState` from external events,
with a FastAPI transport on its own port. The Director consumes replay state to
enforce the project's hardest rule — *never describe replay footage as live*:
while an authoritative replay is active, play-by-play live-action directives are
replaced by an explicit silence decision. `is_live_broadcast` ranks the external
replay signal above the vision replay *hint*, consistent with Server > GSI >
Vision > Inference.

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
├── capture/
│   ├── frame.py       # Module 6: immutable Frame (BGR array + timing)
│   ├── source.py      # FrameSource ABC + SyntheticFrameSource
│   ├── pipeline.py    # threaded, FPS-paced capture loop
│   ├── buffer.py      # thread-safe frame ring buffer
│   ├── timing.py      # FrameClock / FpsMeter / CaptureStats
│   ├── uploader.py    # GPU-aware upload seam + GPU probe
│   ├── factory.py     # build a FrameSource from CaptureSettings
│   └── backends/      # monitor (mss), window, capture card (OpenCV)
├── vision/
│   ├── color.py       # Module 7: NumPy colour statistics (no OpenCV)
│   ├── roi.py         # resolution-independent regions of interest
│   ├── observations.py# VisionObservation / ObservationKind / SceneType
│   ├── state.py       # immutable VisionState (folded cues)
│   ├── fusion.py      # Server > GSI > Vision > Inference primitive
│   ├── pipeline.py    # throttled frame analysis + publish
│   ├── factory.py     # build detectors + pipeline from VisionSettings
│   └── detectors/     # analytic detectors + optional ONNX detector
├── director/
│   ├── directives.py  # Module 10: CommentaryDirective + enums
│   ├── policy.py      # pure speaker/priority/excitement/live-resolution helpers
│   └── director.py    # stateful broadcast-flow controller
├── replay/
│   ├── models.py      # Module 15: ReplayState / ReplayType
│   ├── receiver.py    # framework-agnostic replay-event ingest
│   └── server.py      # FastAPI replay transport
└── ui/
    ├── main_window.py # Module 1: PySide6 shell + navigation
    ├── qt_event_bridge.py
    └── views/         # dashboard, GSI, match, statistics, capture, settings, …
```

## Threading model
- **Qt thread:** owns all widgets. Never touched by network/capture code directly.
- **GSI server thread:** runs uvicorn; parses payloads; publishes events.
- **Capture thread:** runs the FPS-paced capture loop; invokes frame callbacks
  and publishes coarse status/stats. Frames never touch the Qt thread directly —
  the preview is rendered from `latest_frame()` on the ~1 Hz stats tick.
- **Bridge:** `QtEventBridge` subscribes to the bus and re-emits a Qt signal so
  UI updates always happen on the Qt thread.

## Testing
`pytest` drives everything. Domain modules (config, gsi, match, detection,
statistics, persistence, capture, vision, director, replay) have no Qt
dependency and run headless in CI.
The FastAPI endpoint is tested with Starlette's `TestClient`; persistence is
tested against a temp-file SQLite database; the Match Engine is tested end-to-end
by publishing GSI payloads on the bus and asserting on the model, events, stats
and stored rows. The capture pipeline is driven both deterministically (via
`capture_once`) and through a short real-thread lifecycle, using the synthetic
source; backends are tested for clean errors when their native deps are absent.
