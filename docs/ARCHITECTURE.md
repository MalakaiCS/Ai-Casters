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
HUD presence, a heuristic scene classifier, and a **replay-banner detector**.
They need no model, so they are always available and honest about confidence: the
generic scene classifier caps its confidence and won't guess camera type, while
the replay-banner detector *can* assert `SCENE=REPLAY` with real confidence when
the broadcast's on-screen "REPLAY" text is present in its (configurable) region —
detecting the banner's text-edge-on-uniform-background signature, not reading the
word. This stays a *vision hint*: the external replay integration (M5) remains
authoritative and outranks it, and the Director only consults the vision signal
(gated on confidence) when replay integration is unavailable. The **model-backed**
`OnnxObjectDetector` (behind the `[vision]` extra) loads *user-supplied* weights
via onnxruntime; no weights ship with the project, and a missing runtime/model
degrades gracefully to the analytic detectors.

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

## Milestone 6 additions

### Commentary AIs (`commentary/`)
Two `CommentaryGenerator` instances — one per speaker role — subscribe to the
Director's `CommentaryDirectiveIssued` events and turn the directives addressed
to their role into `CommentaryLine`s. Generation runs on a **worker thread** with
a bounded queue: a slow (network) provider never blocks the event bus or the
match/vision pipelines, and when the queue is full the oldest directive is
dropped so commentary stays current rather than lagging.

All backends share one `LLMProvider` interface. The request carries both a
rendered prompt (for API models) and the structured facts (for the template
mock), so the **Mock** provider — the default — generates believable, varied
lines purely from confirmed match facts. That makes it offline, deterministic,
unit-testable, and structurally incapable of inventing facts or imitating a real
caster. Optional **Anthropic** and **OpenAI/local** providers (the `[ai]` extra)
enforce the same rules via their system prompt; the Anthropic path omits sampling
params and `thinking` as Opus 4.8 requires. Robustness is layered: a missing SDK
degrades to Mock at startup, and a provider exception falls back to Mock
mid-line, so an unattended broadcast keeps talking.

## Milestone 7 additions

### Voice engine + audio routing (`voice/`)
The voice subsystem turns each generated `CommentaryLine` into audio. All DSP is
**pure NumPy on a mono float32 buffer** (`voice/audio.py`) — gain, a static
compressor, a three-band EQ (bands partition the signal, so unity gain is exact
identity) and a hard limiter, composed in a per-channel `ChannelDSP` — so the
entire signal path is unit-tested with hand-built arrays and no audio hardware.
TTS sits behind a `TTSEngine` interface: the default **synthetic** engine emits a
short deterministic tone per line (real samples, zero dependencies — it exercises
the queue, DSP, interruption, routing and monitor mix on any machine), and an
optional **system** engine (pyttsx3, `[voice]` extra) renders OS speech.

Each `VoiceChannel` is *completely independent*, per the spec's "two completely
independent voices": its own bounded queue, worker thread, TTS, DSP chain,
volume/mute, broadcast **latency** and **interruption**. Synthesis and playback
run on the worker thread so they never block the bus; a higher-priority line calls
`speak(..., interrupt=True)`, which drains the queue and signals a
`threading.Event` the worker checks between synth, latency wait and device write,
so an in-flight line is abandoned before it reaches the speakers. Output goes
through an `AudioSink` (offline `NullSink` default that records what it received;
optional `SoundDeviceSink` behind `[voice]`), which is what lets each voice target
a **different device** and the whole engine be tested headlessly. A `MonitorMixer`
receives both channels' processed audio at the monitor volume for the caster's
headphones. The `VoiceEngine` owns the two channels + monitor, subscribes to
`CommentaryLineGenerated`, and routes each line to its speaker's channel; TTS and
the sink factory are injectable, which is how the routing is asserted in tests.

### OBS integration (`obs/`)
Scene control sits behind an `OBSController` interface with an offline
`NullOBSController` (records the scenes it was asked to set — the default and the
test double) and a `WebSocketOBSController` that drives real OBS via obsws-python
(`[obs]` extra, lazy-imported). `OBSIntegration` subscribes to the authoritative
`ReplayStateChanged` and, when auto-switching is enabled and OBS is connected,
switches to the replay scene while a replay is active and back to the live scene
when it ends — reusing the same replay signal the Director uses to enforce "never
live during replay", so the picture and the words stay consistent. OBS errors are
swallowed and logged rather than allowed to disrupt the broadcast.

## Milestone 8 additions

### Accounts, licensing, updates, sync (`auth/`, `licensing/`, `updater/`, `sync/`)
The account subsystems all share one shape: a thin **client** that holds state and
publishes events, driving a **backend** behind an interface whose **default
implementation is fully offline**. That is what lets the whole account surface
run, demo and test with no server and no network, while a configured service URL
swaps in an HTTP backend without the client changing. All four HTTP backends share
one dependency-free helper (`core/http.py`, stdlib `urllib`) so the package gains
no runtime HTTP dependency, and a stable per-install **device id**
(`core/identity.py`) ties sessions and license seats together.

- **Auth** (`auth/`): `AuthClient` owns the current `AuthSession`, orchestrating
  login/logout/refresh through an `AuthBackend`. The default `OfflineAuthBackend`
  maps any non-empty credentials to a deterministic local account (explicitly not
  a security boundary — a real deployment configures the HTTP backend). A
  `SessionStore` persists the session for "remember me"; the client restores and,
  if expired, refreshes it on startup. Sign-in state rides the bus as
  `AuthStateChanged`.
- **Licensing** (`licensing/`): tiers → entitlements live in **one table**
  (`tiers.py`), so feature gating everywhere else is a lookup, not scattered
  conditionals; higher tiers are supersets of lower ones. `LicensingClient`
  validates online, and on failure falls back to a **time-boxed offline cache**
  (`cache.py`) so an unreachable service can't lock the operator out mid-broadcast
  — but only within both the license's own expiry and the configured grace window.
  It also lists/deregisters the account's devices (flagging the current one) and
  exposes `is_entitled(feature)` as the app's gate. Changes publish
  `LicenseStateChanged`.
- **Updater** (`updater/`): a dependency-free semantic `Version` (`version.py`)
  drives the comparison; `AutoUpdater.check()` asks the backend for the latest
  release and, only when it is genuinely newer, publishes `UpdateAvailable`. It can
  download and **checksum-verify** an installer but deliberately does *not* silently
  install and relaunch — on Windows that is an installer/OS concern and doing it
  unattended mid-broadcast would be user-hostile, so the updater surfaces the
  update and hands off. The default `NullUpdateBackend` reports nothing, so the app
  never claims a phantom update.
- **Cloud settings sync** (`sync/`): `SettingsSyncClient` pushes/pulls the settings
  document to a per-account store so configuration follows the operator between
  machines. It is gated on the `CLOUD_SYNC` entitlement **and** sign-in; when
  either is absent it is a silent no-op rather than an error. Crucially, a pulled
  document is applied **through the settings manager**, which validates it, so a
  malformed or hostile remote payload can never corrupt the local config.

The composition root constructs each client with its offline-or-HTTP backend
(chosen purely by whether the matching service URL is set) and, on
`start_services`, restores sign-in, validates the license, pulls synced settings
and checks for updates — each wrapped so a failure degrades to offline/free rather
than blocking the broadcast.

## Milestone 9 additions

### Broadcast control (`broadcast/`)
The subsystems (capture, vision, voice) already start and stop independently, but
an operator — and the global hotkeys — need *one* action that turns the whole cast
on or off. `BroadcastController` is that seam: it owns no threads, composes the
subsystems it is given, and announces `BroadcastStateChanged` on the bus, so the
UI and the hotkey manager drive the exact same code path. `start_casting()` is
gated on the `LIVE_CASTING` entitlement — licensing is enforced at the one place it
matters rather than sprinkled through the pipeline. `set_forced_replay()`
deliberately publishes an authoritative `ReplayStateChanged` rather than inventing
a parallel override, so the Director's existing "never live during replay"
enforcement applies unchanged; consequently the *effective* replay state lives on
the Director (which sees both external replay events and forced replay), which is
why diagnostics reads replay state from there.

### Global hotkeys (`hotkeys/`)
The manager maps configured key combinations (`HotkeySettings`) to `HotkeyAction`
callbacks and drives a `HotkeyBackend`. Its `trigger()` invokes an action directly,
so the wiring is verified — and the same actions are reachable from UI buttons —
without any keyboard hook; every callback is wrapped so a hotkey press can never
propagate an exception. The default `NullHotkeyBackend` records bindings but
installs nothing; `PynputHotkeyBackend` (the `[hotkeys]` extra) registers true
OS-global hotkeys, translating `"Ctrl+Alt+C"` to pynput's `"<ctrl>+<alt>+c"` form.

### Diagnostics dashboard (`diagnostics/`)
`DiagnosticsEngine` samples runtime health on a daemon-thread timer (interruptible
wait for immediate shutdown) and publishes an immutable `DiagnosticsSnapshot`. The
`DiagnosticsCollector` reads state through a bundle of small **accessor callables**
(`DiagnosticsSources`) rather than importing the subsystems, so it stays decoupled
and is tested with fakes. Resource sampling uses `psutil` when available and
degrades to the stdlib (memory only) or to `None` — never a fabricated number. The
engine also counts events crossing the bus (excluding its own publications) as a
cheap throughput signal, and `tail_log` reads the rotating log for the in-app
inspector.

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
├── commentary/
│   ├── lines.py       # Modules 11/12: CommentaryLine + event
│   ├── prompts.py     # facts-only, no-imitation prompt builders
│   ├── generator.py   # per-role generator (worker thread)
│   ├── factory.py     # build a provider from AISettings
│   └── providers/     # mock (default), anthropic, openai/local
├── voice/
│   ├── audio.py       # Modules 13/14: AudioClip + pure-NumPy DSP + mix
│   ├── channel.py     # independent voice pipeline (queue/worker/interrupt)
│   ├── engine.py      # VoiceEngine: routes lines to channels + monitor
│   ├── monitor.py     # combined monitor mix
│   ├── sink.py        # AudioSink: NullSink / SoundDeviceSink ([voice])
│   ├── factory.py     # build TTS + output sinks from VoiceSettings
│   └── tts/           # synthetic (default), system (pyttsx3, [voice])
├── obs/
│   ├── controller.py  # Module 16: OBSController (Null / WebSocket [obs])
│   └── integration.py # replay-driven scene switching
├── auth/
│   ├── models.py      # Module 3: Account / AuthSession / AuthResult
│   ├── backend.py     # AuthBackend: Offline (default) / HTTP
│   ├── store.py       # SessionStore ("remember me")
│   └── client.py      # AuthClient (login/logout/refresh/restore)
├── licensing/
│   ├── models.py      # Module 4: tiers, features, License, Device
│   ├── tiers.py       # tier -> entitlements table
│   ├── backend.py     # LicensingBackend: Offline (default) / HTTP
│   ├── cache.py       # time-boxed offline license cache
│   └── client.py      # LicensingClient (validate + device management)
├── updater/
│   ├── version.py     # Module 19: dependency-free semantic version
│   ├── models.py      # UpdateInfo / UpdateCheck
│   ├── backend.py     # UpdateBackend: Null (default) / HTTP manifest
│   └── updater.py     # AutoUpdater (check / download + checksum)
├── sync/
│   ├── backend.py     # SyncBackend: Null (default) / HTTP
│   └── client.py      # SettingsSyncClient (entitlement-gated push/pull)
├── broadcast/
│   └── controller.py  # M9: one-switch casting / mute / forced replay
├── hotkeys/
│   ├── actions.py     # HotkeyAction enum
│   ├── backend.py     # HotkeyBackend: Null (default) / pynput ([hotkeys])
│   └── manager.py     # HotkeyManager (binding + trigger + guard)
├── diagnostics/
│   ├── models.py      # DiagnosticsSnapshot
│   ├── collector.py   # samples subsystems via accessor callables
│   ├── logs.py        # rotating-log tail for the in-app inspector
│   └── engine.py      # timer thread: publish DiagnosticsUpdated
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
- **Voice channel threads:** each voice runs its own worker thread that
  synthesises, processes and plays a line (and applies broadcast latency), so a
  slow TTS or blocking device write never stalls the bus; interruption signals the
  worker to abandon the in-flight line.
- **Diagnostics thread:** a daemon timer thread samples runtime health and
  publishes a snapshot on an interruptible wait, so shutdown is immediate and it
  never keeps a long broadcast from exiting cleanly.
- **Bridge:** `QtEventBridge` subscribes to the bus and re-emits a Qt signal so
  UI updates always happen on the Qt thread.

## Testing
`pytest` drives everything. Domain modules (config, gsi, match, detection,
statistics, persistence, capture, vision, director, replay, commentary, voice,
obs, auth, licensing, updater, sync) have no Qt dependency and run headless in CI.
The voice DSP is tested as pure functions; channels/engine are driven through real
worker-thread lifecycles with the synthetic TTS and null sinks; OBS is tested with
the null controller by publishing replay events and asserting the scene sequence.
The account subsystems are tested entirely through their offline backends —
deterministic login, session persistence, license cache + grace window, tier
entitlements, device management, version/checksum logic, and entitlement-gated
sync push/pull-and-apply — so no test touches the network. The broadcast
controller, hotkey manager and diagnostics engine are tested with fakes and the
null backends (casting lifecycle + entitlement gate, hotkey binding/trigger/guard,
diagnostics collector/engine/log-tail), and a headless full-stack check drives
casting, mute and forced replay through the real hotkey manager on a live
`Application`.
The FastAPI endpoint is tested with Starlette's `TestClient`; persistence is
tested against a temp-file SQLite database; the Match Engine is tested end-to-end
by publishing GSI payloads on the bus and asserting on the model, events, stats
and stored rows. The capture pipeline is driven both deterministically (via
`capture_once`) and through a short real-thread lifecycle, using the synthetic
source; backends are tested for clean errors when their native deps are absent.
