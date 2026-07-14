# AI Esports Caster

Autonomous, professional-quality AI commentary for **Counter-Strike 2**
broadcasts. Once configured the application watches a CS2 observer feed, reads
Game State Integration (GSI), understands the match, and produces two
independent AI voice channels (play-by-play + analyst) routed into OBS — with no
human caster required.

> This is a commercial product under active development. See
> [`docs/ROADMAP.md`](docs/ROADMAP.md) for the milestone plan and
> [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the design.

## Status — Milestones 1–9

**Milestone 1 — Foundation**

- **Project foundation** — installable `ai_caster` package, `src/` layout,
  packaging, tooling, and a headless-CI-friendly test suite.
- **Logging & Diagnostics** — structured, timestamped, rotating logs.
- **Event bus** — thread-safe pub/sub decoupling every module.
- **Settings Manager** — typed/validated/persisted configuration covering all
  configuration areas in the spec.
- **Desktop UI shell** — PySide6 main window with navigation, a live GSI
  monitor, a settings editor, and placeholders for every future module.
- **CS2 GSI Receiver** — FastAPI endpoint that ingests, auth-validates and
  parses GSI payloads, stores the latest live snapshot, and publishes updates on
  the event bus.
- **GSI config generator** — produces the CS2 `.cfg` you drop into the game.

**Milestone 2 — Match State Engine, Statistics, Event Detection**

- **Match State Engine** — the single source of truth: a complete live match
  model (round, score, series, economy/buys, players, bomb) with round history
  and derived **momentum**, **round importance** and **series importance**.
- **Event Detection (GSI)** — kills, deaths, entries, trades, bomb
  plant/defuse/explode, round start/end, score changes, clutch start/win and
  match start/end, each with a confidence score.
- **Statistics Engine** — K/D/A, ADR, HS%, opening kills, trades, clutches and
  multi-kills, from the authoritative snapshot plus events.
- **SQLite persistence** — matches, rounds, events and player stats, with a
  migration-ready schema.
- Live **Match Engine** and **Statistics** views with a real-time event feed.

**Milestone 3 — Video Capture**

- **Capture pipeline** — a threaded, FPS-paced loop feeding an immutable `Frame`
  (BGR NumPy array + timing) through a GPU-aware upload seam into a ring buffer,
  with per-frame callbacks for the vision stack and low-rate stats on the bus.
- **Sources** — a synthetic generator (default; runs anywhere) plus monitor
  (mss), window-by-title, and capture-card (OpenCV) backends that lazy-import
  their native deps. Install with `pip install -e ".[capture]"`.
- **Video Capture view** — start/stop, live FPS/dropped/latency stats and a
  low-rate frame preview.

**Milestone 4 — Computer Vision**

- **Analytic detectors** (classical CV in NumPy, no model) — flash, smoke,
  molotov/fire, kill-feed activity, bomb-timer visibility, HUD presence and a
  heuristic scene/camera classifier, each with an honest confidence score.
- **Optional ONNX object detector** — loads your own weights via the `[vision]`
  extra (`pip install -e ".[vision]"`); no weights ship with the project.
- **Vision pipeline** — consumes captured frames (throttled), produces an
  immutable `VisionState`, and publishes it. Disabled until you enable it.
- **Priority-of-truth fusion** — vision annotates the match model but, per
  Server > GSI > Vision > Inference, never overrides confirmed GSI.
- **Computer Vision view** — live scene classification and cue confidences.

**Milestone 5 — Commentary Director + Replay Integration**

- **Commentary Director** — decides broadcast flow (who speaks, priority,
  excitement, interruptions, handoffs, silence) and emits `CommentaryDirective`s.
  It never writes prose — the M6 AIs turn directives into words.
- **Replay Integration** — a receiver + HTTP endpoint for external replay events
  (started/ended/speed/type) with authoritative replay state.
- **"Never live during replay"** — while a replay is active, play-by-play
  live-action calls become an explicit silence decision.
- **Director & Replay views** — live/replay state, a directive feed, and local
  replay test controls.

**Milestone 6 — Play-by-Play AI + Analyst AI**

- **Two independent commentary generators** turn directives into spoken lines on
  worker threads — facts-only, original wording, never imitating a real caster.
- **Pluggable providers** — a deterministic offline **Mock** (default) plus
  optional **Anthropic** and **OpenAI/local** backends (`pip install -e ".[ai]"`);
  a missing SDK or provider error degrades to Mock so the broadcast keeps talking.
- **Commentary view** — live play-by-play and analyst transcripts with per-channel
  toggles.

**Milestone 7 — Voice Engine, Audio Routing, OBS Integration**

- **Two completely independent voices** — each with its own queue, TTS, dynamics
  chain (compressor, three-band EQ, limiter), volume, mute, broadcast latency and
  interruption (a higher-priority line pre-empts the current one), plus a combined
  monitor mix for the caster's headphones.
- **Audio routing** — each voice targets its own output device; all DSP is pure
  NumPy and runs headless. The default synthetic TTS and offline sinks need
  nothing; real OS speech (pyttsx3) and device output (sounddevice) install with
  `pip install -e ".[voice]"`.
- **OBS Integration** — automatically switches to a replay scene while a replay is
  active and back to live when it ends, driven by authoritative replay state.
  Real OBS control installs with `pip install -e ".[obs]"`; the offline default
  needs nothing.
- **Voice, Audio & OBS view** — per-channel enable/mute/volume with live
  queue/spoken counters and OBS connection/scene status.

**Milestone 8 — Accounts, Licensing, Auto Updater**

- **Authentication** — sign in/out with session persistence ("remember me") and
  automatic restore on startup. The default backend authenticates **locally**, so
  the account surface works fully offline; point it at a real service to go online.
- **Licensing** — subscription tiers (Free/Pro/Studio) mapped to feature
  entitlements, device management, and a time-boxed **offline cache** so an
  unreachable service never interrupts a broadcast. The default backend issues a
  local perpetual Free license — **no payment processing**.
- **Auto updater** — checks a release manifest, announces newer versions, and can
  download + checksum-verify an installer (it surfaces updates rather than
  silently installing). Offline by default.
- **Cloud settings sync** — configuration follows the operator between machines,
  gated on the cloud-sync entitlement and sign-in; incoming settings are validated
  before they are applied.
- **Account, License & Updates view** — sign-in, current tier and entitlements,
  registered devices, and update status.

**Milestone 9 — Full Desktop UI & UX polish**

- **One-switch broadcast control** — go live (start capture + vision together),
  master-mute both voices, or force replay mode from the Dashboard or via global
  hotkeys. Casting is gated on the live-casting entitlement.
- **Global hotkeys** — toggle casting, mute all, force replay. Works from the UI
  out of the box; install `pip install -e ".[hotkeys]"` for true OS-global keys.
- **Diagnostics dashboard** — live uptime, GSI/casting/replay state, capture FPS +
  drop rate, vision throughput, voice queue depth, event throughput and CPU/memory
  (accurate with `pip install -e ".[diagnostics]"`; honest `n/a` without it), plus
  an in-app tail of the application log.
- **Every view is live** — the last placeholder is gone; the full product surface
  is real.

## Quick start

```bash
# 1. Install (dev + UI extras)
python -m pip install -e ".[ui,dev]"

# 2. Run the desktop application
ai-caster
#   ...or:  python -m ai_caster

# 3. Run the test suite (headless; no display or Qt needed)
pytest
```

### Connecting CS2

1. Launch the app and open **Settings → GSI** to confirm the port and auth
   token (defaults: port `3111`, a generated token).
2. Generate the game config:

   ```bash
   python -m ai_caster gsi-config --out gamestate_integration_ai_caster.cfg
   ```

3. Copy the generated file into your CS2 config folder:

   `.../Steam/steamapps/common/Counter-Strike Global Offensive/game/csgo/cfg/`

4. Start CS2. The app's **Live GSI** view updates in real time.

## Repository layout

```
src/ai_caster/   application package (see docs/ARCHITECTURE.md)
tests/           pytest suite (headless)
docs/            roadmap, architecture, GSI notes
```

## Development

```bash
pip install -e ".[ui,dev]"
pytest            # tests
ruff check .      # lint
ruff format .     # format
```
