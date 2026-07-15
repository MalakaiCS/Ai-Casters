<p align="center">
  <img src="../src/ai_caster/ui/assets/logo.png" alt="AI Casters" width="260">
</p>

# AI Casters — Setup Guide

*Commentary. Intelligence. Immersion.*

This guide takes you from a clean machine to a live, AI-cast Counter-Strike 2
broadcast. Everything runs **offline with sensible defaults**; the optional
extras below are only needed for the corresponding real hardware/services.

---

## 1. Prerequisites

- **Python 3.11 or newer** (`python --version`).
- **Windows 10/11** for a production cast (real capture, audio devices, OBS). The
  domain also runs headless on Linux/macOS for development and CI.
- **Counter-Strike 2** with access to an **observer/spectator** feed.
- **OBS Studio** (optional) with the built-in **WebSocket server** for scene
  switching.
- Virtual audio cables (optional) if you want each AI voice on its own device
  (e.g. VB-Audio Cable) — see §6.

---

## 2. Install

```bash
# From the repository root, in a virtual environment:
python -m venv .venv
# Windows:  .venv\Scripts\activate     |  macOS/Linux:  source .venv/bin/activate

# Base install + the desktop UI:
pip install -e ".[ui]"
```

### Optional extras (install only what you need)

| Extra | Adds | When you need it |
|-------|------|------------------|
| `ui` | PySide6 desktop app | Always, for the GUI |
| `capture` | opencv-headless, mss, pygetwindow | Capture a real monitor/window/capture-card |
| `vision` | onnxruntime | Your own ONNX detection model (analytic CV needs nothing) |
| `ai` | anthropic, openai | Real LLM commentary (Mock provider needs nothing) |
| `voice` | pyttsx3, sounddevice | Real OS speech + audio-device output |
| `obs` | obsws-python | OBS scene switching |
| `hotkeys` | pynput | True OS-global hotkeys (UI buttons work without it) |
| `diagnostics` | psutil | Accurate CPU/memory in the dashboard |
| `training` | faster-whisper | Transcribe your own authorized recordings for the offline trainer |
| `dev` | pytest, ruff, httpx | Running the test suite / linters |

Everything at once (a full production box):

```bash
pip install -e ".[ui,capture,vision,ai,voice,obs,hotkeys,diagnostics]"
```

Verify the install:

```bash
ai-caster version
python -m pytest -q          # requires the [dev] extra
```

---

## 3. First run

```bash
ai-caster            # launch the desktop app
# ...or headless equivalents:
ai-caster version
ai-caster gsi-config --out gamestate_integration_ai_caster.cfg
```

On first launch the app writes a settings file and a generated GSI auth token,
starts the GSI receiver, and shows the **Dashboard**. Nothing casts until you
press **Go live**.

---

## 4. Connect Counter-Strike 2 (GSI)

1. Open **Settings → GSI** and note the **port** (default `3111`) and the
   generated **auth token**.
2. Generate the game config:

   ```bash
   ai-caster gsi-config --out gamestate_integration_ai_caster.cfg
   ```

3. Copy the file into your CS2 config folder:

   ```
   .../Steam/steamapps/common/Counter-Strike Global Offensive/game/csgo/cfg/
   ```

4. Start CS2 and load into a match as an **observer**. The **Live GSI** view and
   the Dashboard's *GSI feed* indicator update in real time.

The match engine, statistics and event detection begin working from GSI alone —
no video needed.

---

## 5. Video capture & computer vision (optional)

Vision augments GSI (flash/smoke/fire/kill-feed/HUD/replay-banner cues); it never
overrides confirmed GSI data.

1. Install the `capture` extra.
2. **Settings → Capture**: choose a source — `monitor`, `window` (title match) or
   `capture_card` — and set the matching locator. The default `synthetic` source
   runs anywhere for testing.
3. **Settings → Vision**: enable it and tune per-detector toggles. For the
   on-screen **REPLAY** banner detector, adjust the region fractions to match your
   broadcast overlay. Point `model_path` at an ONNX model only if you have one
   (the `vision` extra); the analytic detectors work without any model.

---

## 6. Audio routing & voices

Two **completely independent** voices (play-by-play + analyst), each with its own
queue, volume, mute, broadcast latency and dynamics chain, plus a combined
monitor mix.

- **Offline default:** the synthetic TTS and null sinks produce/route audio with
  no hardware — good for testing the whole path.
- **Real OS speech:** install the `voice` extra, then in **Settings → Voice** set
  `tts_engine` to `system` (pyttsx3) and assign each channel an `output_device`
  (and a `monitor_device` for your headphones). A common routing is
  *play-by-play → Cable A*, *analyst → Cable B*, *monitor → headphones*, with the
  cables captured in OBS.
- **Production voices (ElevenLabs):** set `tts_engine` to `elevenlabs`, paste your
  key into `elevenlabs_api_key`, and (optionally) pick a `elevenlabs_model`
  (`eleven_turbo_v2_5`/`eleven_flash_v2_5` are the low-latency options). Each
  channel can be given a different ElevenLabs `voice_id` so play-by-play and
  analyst sound distinct. If the key is missing or a request fails, the engine
  falls back to the offline synthetic voice rather than going silent.
- Per-channel compressor/EQ/limiter and volume/mute live in the same section and
  in the **Voice, Audio & OBS** view.

---

## 7. OBS integration (optional)

1. In OBS: **Tools → WebSocket Server Settings** → enable, note the port
   (default `4455`) and password.
2. Install the `obs` extra.
3. **Settings → Audio & OBS**: enable it, enter host/port/password, turn on
   **auto-switch scenes**, and set the **live** and **replay** scene names. When a
   replay is active the app switches to the replay scene and back to live when it
   ends.

---

## 8. Go live, hotkeys & controls

- **Dashboard → Go live** starts capture + vision together and begins casting.
  **Mute all** and **Force replay** are next to it.
- **Global hotkeys** (install the `hotkeys` extra for OS-global keys; the buttons
  work regardless):

  | Action | Default |
  |--------|---------|
  | Toggle casting | `Ctrl+Alt+C` |
  | Mute all | `Ctrl+Alt+M` |
  | Force replay mode | `Ctrl+Alt+R` |

  Rebind them in **Settings → Hotkeys**.

---

## 9. Commentary AI provider

- **Default:** the offline **Mock** provider — deterministic, fact-safe, no API
  key, never imitates a real caster.
- **Real LLM:** install the `ai` extra and set **Settings → AI** `provider` to
  `anthropic` or `openai`/`local`, with an API key (and base URL for local
  OpenAI-compatible servers). A missing SDK or a provider error degrades back to
  Mock mid-broadcast so the show keeps talking.

---

## 10. Accounts, roles, licensing & updates

- **Sign-in is required.** On launch the app shows a boot window — **sign in**,
  **create an account**, or **forgot password** — and only opens once you have a
  real session (a saved session is restored automatically). Distributed builds are
  **Supabase-only**: a build without a configured account service refuses sign-in
  rather than accepting anything, so you must ship it with Supabase configured
  (bake the `SUPABASE_URL`/`SUPABASE_ANON_KEY` secrets — see [`SUPABASE.md`](SUPABASE.md)).
  For local development (running from source, not a packaged build) an offline
  backend is used so you can sign in with any valid email + password.
- **Roles.** Every user has a role — **Owner, Founder, Admin, Staff, Partner** or
  **User** (the default). Roles gate features: **Staff and above** can open
  **Train the AI**; **Admin and above** can open **Team & Roles** to promote or
  demote others (a manager can only assign roles below their own). Roles live in
  Supabase; set your first **Owner** once via SQL, then manage everyone in-app —
  see [`SUPABASE.md` §5c](SUPABASE.md).
- **Account & License** view: see your tier and entitlements, manage devices, and
  sign out.
- Subscription tiers gate features (e.g. cloud sync is Studio-tier). Licensing has
  an offline grace cache so an unreachable service won't interrupt a broadcast.
  **No payment processing** is included.
- **Updates:** on startup (and via **Check for updates**) the app fetches a JSON
  release manifest, compares it to the running version, and surfaces newer
  releases — it never installs silently. Official builds are pre-wired: the release
  workflow publishes `manifest.json` alongside the installer and serves it from the
  stable `…/releases/latest/download/manifest.json` URL, which is baked into the
  build's deploy defaults. To point at your own manifest, set
  **Settings → `updater.manifest_url`**. Each release's manifest carries the
  installer URL and its SHA-256, which the updater verifies before handing the
  download on to install.

---

## 11. Diagnostics

The **Diagnostics** view shows live uptime, GSI/casting/replay state, capture FPS
and drop rate, vision throughput, voice queue depth, CPU/memory (accurate with the
`diagnostics` extra) and event throughput, plus a tail of the application log.

---

## 12. Training the AI (in-app for Staff+, or the CLI)

The app learns **general** pacing/vocabulary from **authorized** sources. It never
clones a voice, never models an identifiable person, and only ever *suggests*
settings for review.

**In the app (Staff and above):** open **Train the AI**. Add authorized transcript
folders and/or recordings you own (with a consent reference), click **Analyze**,
and review the learned style. The **Tone & pacing** panel sets baseline excitement,
the minimum gap between lines (when to hold back) and whether the play-by-play may
interrupt — these apply to the live director as soon as you save. Transcribing
recordings in-app needs the `training` extra (`faster-whisper`); transcript-folder
training and the tone/pacing controls need nothing extra.

**From the CLI (any environment):**

```bash
ai-caster train ./transcripts --out style-profile.json
```

Each `*.json` transcript must carry authorization and text-only segments:

```json
{
  "source_id": "grandfinal-2025",
  "language": "en",
  "authorization": {"authorized": true, "consent_reference": "LEAGUE-CONSENT-2025-014"},
  "segments": [
    {"role": "play-by-play", "text": "Down to the wire on the bomb site", "start": 0.0, "end": 3.2},
    {"role": "analyst", "text": "The positioning here is textbook", "start": 3.8, "end": 6.5}
  ]
}
```

Unauthorized or audio-bearing files are refused (or skipped with
`--skip-unauthorized`). The exported profile is aggregate, anonymized statistics
and can *suggest* Director pacing values for you to review — it is never applied
automatically.

### Learning from real recordings (authorized only)

You can also learn general pacing from **recordings you own or are licensed to
use** — the recording is transcribed locally to *text + timing* and folded
through the same anonymization; **no voice model is ever built and no speaker is
identified.** Install the training extra (`pip install -e ".[training]"`, which
adds `faster-whisper`) and point `--media` at a local file or a direct link to
your own upload:

```bash
ai-caster train --media ./casts/final.wav --media ./casts/semis.mp4 \
  --consent-ref "OWN-RECORDING-2026-004" --rights-holder "My Team" \
  --out style-profile.json
```

- `--consent-ref` is **required** with `--media`: it is your affirmation that you
  hold the rights to those recordings.
- **Third-party platform links are refused.** YouTube / Twitch / TikTok / etc.
  URLs are rejected outright — downloading someone else's broadcast is a rights
  problem, not a feature. Use your own recordings or clips you are licensed to use.
- `--media` and a transcript directory can be combined in one run; use
  `--whisper-model` (default `base`) and `--language` (default `en`) to tune
  transcription.

---

## 13. Where settings & data live

Resolved via `platformdirs` per user, or under a single root when the
`AI_CASTER_HOME` environment variable is set (handy for portable installs/tests):

| File | Location | Purpose |
|------|----------|---------|
| `settings.json` | config dir | All configuration |
| `session.json` | config dir | Saved sign-in ("remember me") |
| `device.json` | config dir | Stable device id |
| `license.json` | cache dir | Offline license cache |
| `ai_caster.sqlite` | data dir | Matches, rounds, events, stats |
| `ai_caster.log` | log dir | Rotating application log |

```bash
# Portable / test install — keep everything under one folder:
AI_CASTER_HOME=./ai-casters-home ai-caster
```

---

## 14. Troubleshooting

- **"Desktop UI unavailable"** — install the UI extra: `pip install -e ".[ui]"`.
- **GSI port already in use** — change the port in **Settings → GSI** and
  regenerate the `.cfg`.
- **No GSI feed** — confirm the `.cfg` is in the CS2 `cfg` folder, you're
  observing a match, and the port/token match Settings.
- **No real audio / device errors** — install the `voice` extra and pick valid
  output devices; the app falls back to silent null sinks otherwise.
- **OBS not switching** — enable the OBS WebSocket server and check
  host/port/password; OBS errors are logged but never interrupt the cast.
- **Hotkeys do nothing globally** — install the `hotkeys` extra; the on-screen
  buttons work without it.
- **Casting blocked** — your subscription tier may not include live casting; check
  the **Account & License** view.
