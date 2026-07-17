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

1. Open **Settings → GSI**.
2. Click **Install GSI config into CS2** — it finds your CS2 folder and drops the
   config in automatically. (If it can't find CS2, use **Export config to a
   folder…** and copy the file into
   `.../Counter-Strike Global Offensive/game/csgo/cfg/` yourself.)
3. **Fully restart CS2** (quit the game, not just the map) and load into a match as
   an **observer**. The **Live GSI** view and the Dashboard's *GSI feed* indicator
   update in real time.

> **Using a HUD manager (Lexogrine, etc.)?** No conflict — CS2 sends GSI to *every*
> `gamestate_integration_*.cfg` at once, so ours runs alongside theirs. If the feed
> still says "waiting", it almost always means our config isn't in the cfg folder
> yet or CS2 wasn't fully restarted after installing it.

The CLI equivalent is `ai-caster gsi-config --out gamestate_integration_ai_caster.cfg`.

The match engine, statistics and event detection begin working from GSI alone —
no video needed.

---

## 5. Video capture & computer vision (optional)

Vision augments GSI (flash/smoke/fire/kill-feed/HUD/replay-banner cues); it never
overrides confirmed GSI data.

1. Install the `capture` extra.
2. **Video Capture view**: pick **Capture from** — `Monitor / screen`, `Window`
   (title match), `Capture card` or `Synthetic` (test pattern). For a monitor,
   choose which display from the **Monitor** dropdown (it lists your connected
   screens with resolution; hit **Rescan** if you plug one in). Click **Apply
   source** to save it, then **Refresh preview** to see exactly what the caster
   will be looking at *before* you go live — no need to start a full capture to
   check you picked the right screen. The default `synthetic` source runs anywhere
   for testing.
3. **Settings → Vision**: enable it and tune per-detector toggles. For the
   on-screen **REPLAY** banner detector, adjust the region fractions to match your
   broadcast overlay. Point `model_path` at an ONNX model only if you have one
   (the `vision` extra); the analytic detectors work without any model.

---

## 5b. Rehearsal mode — record & replay a match

You don't need a live CS2 match in front of you to test the cast. The **Rehearsal**
view lets you:

- **Record** the live GSI feed to a `.jsonl` clip while a real match (or a demo)
  plays. The clip is saved under your data folder's `recordings/`; the GSI auth
  token is stripped, so a clip is safe to keep or share.
- **Replay** any saved clip back through the *entire* pipeline — match model,
  director, banter, voices — at **0.5× / 1× / 2× / 4× / Instant**. Because it drives
  the same path as a live feed, it's the fastest way to tune voices, excitement,
  reaction contrast, and the downtime/slow-round filler, and it runs on any machine
  with no CS2 open. A progress bar tracks playback; **Stop** ends it early.

Record one good match once, then iterate on your commentary settings against it
as many times as you like.

---

## 6. Audio routing & voices

Two **completely independent** voices (play-by-play + analyst), each with its own
queue, volume, mute, broadcast latency and dynamics chain, plus a combined
monitor mix.

- **Offline default:** the synthetic TTS and null sinks produce/route audio with
  no hardware — good for testing the whole path.
- **Just play it through my headset:** in the **Voice, Audio & OBS** view click
  **Play through default headset / speakers** — both casters and the monitor mix
  route to your default Windows output, no device names to configure. (Pair it
  with a real voice: set the engine to **System** for offline speech or
  **ElevenLabs** for production voices — *Synthetic* only plays a test tone.)
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

Controlled from the **OBS Integration** panel in the **Voice, Audio & OBS** view.

1. In OBS: **Tools → WebSocket Server Settings** → **Enable WebSocket server**, then
   note the **Port** (default `4455`) and click **Show Connect Info** for the
   **password**. (If you don't set a password in OBS, leave the app's password blank.)
2. In the app's **OBS Integration** panel: tick **Enable OBS integration**, enter the
   **host** (`127.0.0.1` if OBS is on the same PC), **port** and **password**, then
   click **Connect**. The status line shows *connected* and the **current scene**;
   any connection error (OBS closed, WebSocket off, wrong port/password) is shown
   right there so you can fix it.
3. Click **Refresh scenes** to pull your scene list, then pick the **Live scene** and
   **Replay scene** from the dropdowns. Two independent modes:
   - **Auto-switch scenes** — *the app drives OBS*: it switches to the replay scene
     while a replay is active and back to live when it ends.
   - **Recognise the replay scene** — *the app reads OBS*: if your **HUD manager**
     (Lexogrine, etc.) is the one switching OBS to a replay scene, tick this and set
     **Replay scene** to that scene's name. The app watches OBS's current scene and,
     while it's on the replay scene, treats the broadcast as a replay so the casters
     never describe it as live. Leave auto-switch **off** when the HUD is driving.
   **Save** persists everything for next launch.

> If the panel says the OBS control library "isn't available in this build",
> reinstall the latest version — the official installer now bundles it.

### What the casters understand about sides

The AI knows how CS2 decides starting sides and will set the stage correctly:

- **Knife round** — detected automatically (everyone holding only knives). The desk
  calls it out and notes that **the winner picks which side to start**.
- **Best-of-1** — the casters note the **knife round decides sides**.
- **Best-of-3 / Best-of-5** — they note that **the team that didn't pick the map
  chooses which side to start**, using the series format reported by GSI.

---

## 8. Go live, hotkeys & controls

- **Dashboard → Go live** starts capture + vision together and begins casting.
  **Mute all** and **Force replay** are next to it.
- **Start casting from** (Dashboard, next to Go live) picks *when* the desk begins
  talking each match:
  - **ASAP** — immediately, warm-up included (default).
  - **Knife round** — hold until the knife round begins (or the first live round if
    there's no knife round).
  - **Round 1** — hold until the first scored round, skipping warm-up *and* the
    knife round.
  The setting re-arms every new match, so it applies to each game you cast.
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
- **Less repetition:** both casters now vary their wording. The offline (Mock)
  provider rotates through several phrasings per situation so you don't hear the
  same line every bomb plant, and the real LLM providers are given the last few
  spoken lines and told to say something fresh.
- **The two casters talk to each other (banter):** they now share a live desk
  transcript, so the analyst can build on what the play-by-play just said instead
  of two announcers talking in isolation. On a marquee moment (a clutch), the
  play-by-play makes the call and the analyst chimes straight in with a reaction —
  never interrupting the caller. With a real LLM the reactions are free-form; the
  offline provider adds a light lead-in ("Right —…") so the exchange still reads
  as a conversation.

### Downtime commentary (timeouts, pauses & breaks)

When there's no live action — a **called timeout**, a **paused** match, **half-time**
or **warm-up** — the desk keeps talking instead of going silent: the analyst covers
*what to expect from the team that called the timeout*, and the play-by-play caster
keeps things warm with the score and a stat or two. It waits a few seconds into the
lull before starting, never interrupts live action, and yields entirely to replays.
Tune or disable it under `downtime` in settings (`enabled`, `min_delay_seconds`,
`interval_seconds`).

### Slow-round filler (quiet live rounds)

Some rounds are slow and methodical — long stretches of a live round with no kills
or plants. Rather than let those go silent, the desk adds light filler after a
short quiet spell: the analyst talks map control and the economy read, and the
play-by-play caster keeps the score and momentum in the picture. It only speaks
during genuine live play (never over freeze-time, timeouts, or replays), stays
low-key and non-interrupting, and resets the moment real action happens again.
Tune or disable it under `downtime` (`slow_round_enabled`,
`slow_round_after_seconds`, `slow_round_interval_seconds`).

---

## 10. Accounts, roles, licensing & updates

- **Sign-in is required.** On launch the app shows a boot window — **sign in**,
  **create an account**, or **forgot password** — and only opens once you have a
  real session (a saved session is restored automatically). Your signed-in email
  and role show at the **top-right of the window**; the button there signs you out,
  and **signing out drops you straight back to the login / sign-up window**. (The
  Account page no longer duplicates login/create-account — it just shows your
  session and a sign-out.) Distributed builds are
  **Supabase-only**: a build without a configured account service refuses sign-in
  rather than accepting anything, so you must ship it with Supabase configured
  (bake the `SUPABASE_URL`/`SUPABASE_ANON_KEY` secrets — see [`SUPABASE.md`](SUPABASE.md)).
  For local development (running from source, not a packaged build) an offline
  backend is used so you can sign in with any valid email + password.
- **Roles.** Every user has a role — **Owner, Founder, Admin, Staff, Partner** or
  **User** (the default). Roles gate features, grouped under an **Admin** section in
  the sidebar that a plain **User never sees**: **Staff and above** get **Train the
  AI**; **Admin and above** also get **Team & Roles** to promote or demote others (a
  manager can only assign roles below their own). The sidebar updates the moment your
  role does (sign-in, or the background role refresh). Roles live in Supabase; set
  your first **Owner** once via SQL, then manage everyone in-app —
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
folders, recordings you own, **YouTube links**, and/or **paste a transcript**
directly into the text box (with a consent reference), click **Analyze**, and
review the learned style. Analysis also **splits what's relevant for play-by-play
vs analytical casting** — pasted lines can be labelled (`PBP:` / `Analyst:`) or
are sorted automatically by their language, and the results show each role's pace
and top terms. The **Tone & pacing** panel sets
baseline excitement, the minimum gap between lines (when to hold back) and whether
the play-by-play may interrupt — these apply to the live director as soon as you
save. Transcribing recordings and fetching YouTube captions in-app need the
`training` extra (`faster-whisper` + `youtube-transcript-api`); transcript-folder
training and the tone/pacing controls need nothing extra.

> **YouTube links use captions only.** The app reads the video's existing caption
> transcript (text + timing) — it never downloads audio/video and never captures a
> voice, so the "no voice cloning" guarantee holds. You must own the content or be
> licensed to use it (your own channel, or Creative-Commons material); the app asks
> you to confirm this before adding a link. Coverage depends entirely on the video's
> captions — a video with sparse or no captions yields little text; **local
> recordings + Whisper give far better coverage** for long material.

**Share it with everyone — the team hub.** After analyzing, click **Publish to
team hub** to push the trained style to a shared table (Supabase, Staff+ only).
**Every app pulls the latest published style on launch** and casts with it by
default — so anyone on the account is productive immediately without training
anything themselves. See [`SUPABASE.md` §5d](SUPABASE.md) for the one-time SQL.

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
