# AI Esports Caster

Autonomous, professional-quality AI commentary for **Counter-Strike 2**
broadcasts. Once configured the application watches a CS2 observer feed, reads
Game State Integration (GSI), understands the match, and produces two
independent AI voice channels (play-by-play + analyst) routed into OBS — with no
human caster required.

> This is a commercial product under active development. See
> [`docs/ROADMAP.md`](docs/ROADMAP.md) for the milestone plan and
> [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the design.

## Status — Milestones 1 & 2

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
