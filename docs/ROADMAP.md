# AI Esports Caster — Development Roadmap

This document breaks the project into sequential milestones. Each milestone
must **compile, run and be fully testable** before the next one begins.
Approval is requested before starting each new milestone.

The architecture target is a **modular, production-ready commercial desktop
application** (not a prototype). Modules communicate through clean interfaces
and an internal event bus. **No module depends directly on UI code.**

---

## Module Inventory (from the master specification)

| # | Module | Milestone |
|---|--------|-----------|
| 1 | Desktop UI | M1 (shell), M9 (full) |
| 2 | Settings Manager | M1 |
| 3 | Authentication Client | M8 |
| 4 | Licensing Client | M8 |
| 5 | GSI Receiver | M1 |
| 6 | Video Capture | M3 |
| 7 | Computer Vision | M4 |
| 8 | Match State Engine | M2 |
| 9 | Event Detection | M2 / M4 |
| 10 | Commentary Director | M5 |
| 11 | Play-by-Play AI | M6 |
| 12 | Analyst AI | M6 |
| 13 | Voice Engine | M7 |
| 14 | Audio Routing | M7 |
| 15 | Replay Integration | M5 |
| 16 | OBS Integration | M7 |
| 17 | Statistics Engine | M2 |
| 18 | Training Pipeline (offline) | M10 |
| 19 | Auto Updater | M8 |
| 20 | Logging & Diagnostics | M1 |

---

## Milestones

### ✅ Milestone 1 — Foundation, Shell, Configuration, GSI Receiver
**Goal:** a running desktop application skeleton that can receive and display
live CS2 Game State Integration data, with a validated configuration system and
production-grade logging.

Deliverables:
- Project scaffolding (src layout, packaging, tooling, CI-ready test suite).
- **Logging & Diagnostics** (Module 20): timestamped, structured, rotating logs.
- Internal **event bus** for decoupled module communication.
- **Settings Manager** (Module 2): typed, validated, persisted configuration
  covering every configuration area in the spec.
- **Desktop UI shell** (Module 1, partial): PySide6 main window with navigation
  and placeholder views for every future module, plus a live GSI monitor view
  and a settings editor view.
- **GSI Receiver** (Module 5): FastAPI HTTP endpoint that ingests CS2 GSI
  payloads, validates the auth token, parses them into typed models, stores the
  latest live snapshot, and publishes updates on the event bus.
- CS2 GSI **config-file generator** (the `.cfg` you drop into the game).
- Unit tests for config, GSI parsing, the GSI endpoint and the event bus.

### ✅ Milestone 2 — Match State Engine, Statistics, Event Detection (GSI-based)
**Goal:** turn the latest-snapshot store into the full single source of truth.

Deliverables:
- **Match State Engine** (Module 8): rebuilds the complete `LiveMatch` model on
  every payload (round, score, series, economy/buys, players, bomb, observed
  player) with round **history**, and derived **momentum**, **round importance**
  and **series importance**. Honours the Server > GSI > Vision > Inference rule.
- **Event Detection** (Module 9, GSI portion): diff-based detection of kills,
  deaths, entries, trades, bomb plant/defuse/explode, round start/end, score
  changes, clutch start/win, and match start/end — with confidence scores.
- **Statistics Engine** (Module 17): per-player K/D/A, ADR, HS%, opening kills,
  trades, clutches won and multi-kills from the authoritative snapshot + events.
- **SQLite persistence**: matches, rounds, events and player stats, with a
  migration-ready schema and a repository that keeps all SQL in one place.
- Two new live UI views (Match Engine, Statistics) plus an event feed.
- Unit + integration tests for the model, detector, statistics, persistence and
  the end-to-end engine.

### ✅ Milestone 3 — Video Capture
**Goal:** capture the CS2 observer feed into a timed, GPU-aware frame pipeline —
the input the M4 computer-vision system consumes.

Deliverables:
- **Frame model + sources**: an immutable `Frame` (BGR NumPy array + timing) and
  a `FrameSource` abstraction. A **synthetic** source is the default so the whole
  app runs on any machine (incl. headless CI); real backends capture a
  **monitor** (mss), a **window** by title (mss + pygetwindow) or a
  **capture card** (OpenCV), each lazy-importing its native dependency.
- **Capture pipeline**: a threaded, FPS-paced loop with a ring **buffer** for
  frame look-back, per-frame callbacks for high-rate consumers, and low-rate
  status/stats on the bus. Never blocks the UI thread.
- **Timing & stats**: target-vs-actual FPS, dropped frames, average capture
  latency and uptime, with the pacing math split out for deterministic testing.
- **GPU-aware seam**: an injectable `FrameUploader` (CPU no-op default) plus a
  real GPU probe, so M4 can plug in CUDA upload without touching the pipeline.
- **Config + UI**: a `CaptureSettings` section and a Video Capture view with
  start/stop, live stats and a low-rate frame preview.
- Unit + threaded tests for the frame, source, buffer, timing, pipeline and
  factory (incl. clean errors when native deps are absent).

### ✅ Milestone 4 — Computer Vision
**Goal:** watch the captured feed and produce confidence-scored observations,
fused into the Match Engine without ever overriding confirmed GSI.

Deliverables:
- **Detector interface + analytic detectors** (classical CV in NumPy, no model,
  always available): flash, smoke, molotov/fire, kill-feed activity, bomb-timer
  visibility, HUD presence, and a heuristic scene/camera classifier — each
  emitting a `VisionObservation` with an honest confidence.
- **Resolution-independent ROI system** and NumPy colour statistics.
- **Optional ONNX object detector** behind the `[vision]` extra: loads
  user-supplied weights (none ship with the project); a bad path degrades to the
  analytic detectors instead of crashing.
- **Vision pipeline**: consumes captured frames as a callback, throttles to a
  configured analysis rate, downscales, runs detectors, folds results into an
  immutable `VisionState`, and publishes it (disabled by default).
- **Priority-of-truth fusion**: a tested `fuse`/`fuse_effect` primitive encoding
  Server > GSI > Vision > Inference; the engine attaches the latest `VisionState`
  to the match model as an **annotation only** — GSI fields are never overridden.
- **Config + UI**: expanded `VisionSettings` (per-detector toggles, model path)
  and a Computer Vision view showing scene, cues and confidences.
- Unit tests for colour, ROI, every detector, state assembly, fusion, the
  pipeline (analysis/throttle/attach), the ONNX guard paths and engine fusion.

### ✅ Milestone 5 — Commentary Director + Replay Integration
**Goal:** an internal controller that governs broadcast flow (it decides, it
never speaks), plus authoritative replay integration that enforces the hard rule
*never describe replay footage as live.*

Deliverables:
- **Commentary Director** (Module 10): consumes match events, the live model,
  vision and replay state and emits `CommentaryDirective` decisions — speaker
  selection (play-by-play vs. analyst), priority, excitement (scaled by round
  importance), interruption/cancellation, rate-limited silence, and post-round
  handoffs. Pure policy helpers make every decision testable.
- **Replay Integration** (Module 15): a framework-agnostic `ReplayReceiver` for
  external replay events (started/ended/speed/type) with a FastAPI transport on
  its own port, publishing authoritative `ReplayStateChanged`.
- **"Never live during replay" enforcement**: while an authoritative replay is
  active, play-by-play "call live action" directives are replaced with an
  explicit silence decision. A tested `is_live_broadcast` primitive honours the
  priority of truth (external replay > vision guess).
- **Config + UI**: `min_speech_gap_ms` setting; Commentary Director view (live
  vs. replay state + directive feed) and a Replay view (state + local test
  controls).
- Unit tests for replay (models/receiver/HTTP), the pure policy, and the
  Director's routing/interruption/handoff/silence/replay behaviour.

### ✅ Milestone 6 — Play-by-Play AI + Analyst AI
**Goal:** two independent commentary generators that turn the Director's
directives into spoken words — original wording, no fact invention, no imitation
of identifiable real casters.

Deliverables:
- **Two generators** (Modules 11 & 12), one per speaker role, each consuming the
  directives addressed to it and generating on a **worker thread** so a slow
  provider never blocks the pipelines (stale directives are dropped, not queued).
- **Pluggable providers** behind one interface: a deterministic **Mock**
  template engine (default, offline, fact-safe by construction) plus optional
  **Anthropic** and **OpenAI/local** backends behind the `[ai]` extra. A missing
  SDK degrades to Mock; a provider error falls back to Mock mid-broadcast.
- **Prompts** that encode the hard rules (facts-only, original wording, no caster
  imitation, output only the line) — and Anthropic usage that omits sampling
  params/thinking as those models require.
- **Config + UI**: provider/model/base-url/max-tokens settings and a Commentary
  view with the two live transcripts and per-channel enable toggles.
- Unit tests for the mock, prompts, factory fallback, and generator routing/
  fallback/worker behaviour.

### ✅ Milestone 7 — Voice Engine, Audio Routing, OBS Integration
**Goal:** speak the generated commentary through two fully independent voices,
route each voice to its own audio output, and drive OBS scene changes from the
authoritative replay state.

Deliverables:
- **Audio + DSP core** (pure NumPy, fully unit-tested, no hardware): an immutable
  `AudioClip` plus per-channel dynamics — gain, static compressor, three-band EQ
  and a hard limiter — chained in a `ChannelDSP`, and a `mix` primitive for the
  monitor feed.
- **Pluggable TTS** behind one interface: a deterministic offline **synthetic**
  engine (default — exercises the whole voice path with real samples and zero
  dependencies) and an optional **system** engine (pyttsx3) behind the `[voice]`
  extra; a missing SDK degrades to synthetic.
- **Two completely independent voice channels** (Module 13): each owns its queue,
  worker thread, TTS, DSP chain, per-channel volume/mute, broadcast **latency**
  and **interruption** (a higher-priority line pre-empts the in-flight one), so
  synthesis and playback never block the bus.
- **Audio routing** (Module 14): a per-channel `AudioSink` (offline `NullSink`
  default; optional `SoundDeviceSink` behind `[voice]`) lets each voice target a
  different device, plus a combined **monitor mix** for the caster's headphones.
- **Voice Engine**: subscribes to generated lines and routes each to its speaker's
  channel (honouring interruption); TTS and sinks are injectable so the whole
  engine runs and is tested headlessly.
- **OBS Integration** (Module 16): an `OBSController` interface with an offline
  `NullOBSController` default and a `WebSocketOBSController` (obsws-python, `[obs]`
  extra); an integration layer switches to the replay scene while a replay is
  active and back to live when it ends, driven by authoritative `ReplayStateChanged`.
- **Config + UI**: per-channel voice/DSP settings, OBS scene settings, and a
  Voice/Audio & OBS view (per-channel enable/mute/volume + live counters, OBS
  status) replacing the M7 placeholders.
- Unit tests for the DSP/mix, channel queue/interruption/latency/monitor, engine
  routing, and OBS null-controller + replay-driven scene switching, plus a
  headless full-stack check (commentary lines → both voices + monitor; replay →
  OBS scene flip).

### ✅ Milestone 8 — Accounts, Licensing, Auto Updater
**Goal:** sign the operator in, resolve what their subscription unlocks, keep
their configuration in sync, and surface application updates — all fully usable
offline, with no payment processing.

Deliverables:
- **Authentication Client** (Module 3): sign-in/out and session management behind
  an `AuthBackend` interface. The default backend authenticates **locally**
  (offline, deterministic, no server) so the account surface works everywhere; an
  HTTP backend targets a real account service. The client persists the session
  for "remember me" and restores/refreshes it on startup.
- **Licensing Client** (Module 4): license validation with **subscription tiers**
  (Free/Pro/Studio) mapped to **feature entitlements** via one table, **device
  management** (list/deregister seats, current device flagged), and a **time-boxed
  offline cache** so an unreachable service never locks the operator out
  mid-broadcast. The default backend issues a local perpetual Free license.
- **Auto Updater** (Module 19): compares the running build to a release manifest,
  announces newer versions on the bus, and can download + **checksum-verify** an
  installer. It surfaces updates rather than silently installing — the honest
  boundary for an unattended tool. The default backend reports no updates offline.
- **Cloud settings sync**: pushes/pulls the settings document to a per-account
  store so configuration follows the operator between machines. Gated on the
  `CLOUD_SYNC` entitlement and sign-in; pulled documents are validated through the
  settings manager before they are applied. Default backend is a local no-op.
- **Stable device identity**: a per-install id persisted under the config dir,
  tying sessions and license seats together.
- **Config + UI**: Account/Licensing/Updater/Sync settings sections and an
  **Account, License & Updates** view (sign-in, tier + entitlements, devices,
  update status) replacing the M8 placeholder.
- Unit tests for the offline auth/licensing backends, session store, license
  cache + grace window, entitlement tiers, device management, version compare +
  checksum, and sync gating/push/pull-and-apply — plus a headless full-stack
  check and the composition-root wiring. All backends degrade gracefully and no
  payment processing is present.

### ✅ Milestone 9 — Full Desktop UI & UX polish *(current)*
**Goal:** finish the desktop surface — every module has a real, live view — and add
the operator ergonomics that make long unattended broadcasts practical: one-switch
broadcast control, global hotkeys, and a runtime diagnostics dashboard.

Deliverables:
- **Broadcast controller**: one "go live" switch that starts/stops the whole cast
  (capture + vision) together, master-mutes both voices, and forces replay mode —
  the single code path shared by the UI and the hotkeys. Casting is gated on the
  `LIVE_CASTING` entitlement; forced replay reuses the authoritative
  `ReplayStateChanged` machinery so the Director's "never live during replay"
  enforcement applies unchanged.
- **Global hotkeys** (Module 1 completion): configured combinations map to the
  broadcast actions (toggle casting, mute all, force replay). The default backend
  installs no OS hook — the actions stay reachable from the UI — while an optional
  `pynput` backend registers true global hotkeys behind the `[hotkeys]` extra. A
  hotkey callback can never crash the app.
- **Diagnostics dashboard** (Module 20 completion): a background engine samples
  runtime health (uptime, GSI/casting/replay state, capture FPS + drop rate,
  vision throughput, voice queue depth, event throughput, CPU/memory) into an
  immutable snapshot published on a timer, plus an in-app tail of the rotating log.
  CPU/memory use `psutil` when present (`[diagnostics]` extra) and degrade honestly
  to `None` rather than a fabricated figure.
- **Full desktop UI**: the last placeholder is gone — every navigation entry is a
  live view. The Dashboard gains broadcast controls and live state; a new
  Diagnostics view renders the metrics and log.
- **Long-session stability**: the diagnostics engine runs on a daemon thread with
  an interruptible wait (immediate, clean shutdown), and the composition root
  disposes diagnostics, hotkeys and the broadcast controller in order on stop.
- Unit tests for the broadcast lifecycle/entitlement-gate/mute/forced-replay, the
  hotkey binding/trigger/guard and pynput translation, and the diagnostics
  collector/engine/log-tail — plus a headless full-stack check driving casting,
  mute and forced replay through the hotkeys and asserting the diagnostics
  snapshot. UI verified by byte-compile + slot wiring (Qt can't load headless).

### Milestone 10 — Offline Training Pipeline
Offline analysis of **authorized** recordings for general timing/pacing/vocab
learning. No voice cloning or imitation of identifiable individuals. Not part of
the live casting engine.

---

## Cross-cutting principles
- Clean architecture, dependency injection at the composition root (`app.py`).
- Every module independently testable; no UI coupling in domain modules.
- Priority of truth: **Server events > GSI > Vision > Inference.**
- Everything timestamped and logged.
- Performance target: 1080p60, real-time, stable long-duration broadcasts.
