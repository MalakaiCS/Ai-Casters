# CS2 Game State Integration (GSI) setup

The application receives live match data from Counter-Strike 2 via **Game State
Integration**. CS2 activates GSI when a `gamestate_integration_*.cfg` file is
present in its config directory.

## 1. Generate the config

The token and port must match the running app (see **Settings → GSI**). Generate
a config that already matches your settings:

```bash
python -m ai_caster gsi-config --out gamestate_integration_ai_caster.cfg
```

Or export it from the UI: **Settings → Export CS2 GSI config…**

## 2. Install it into CS2

Copy the generated file into:

```
.../Steam/steamapps/common/Counter-Strike Global Offensive/game/csgo/cfg/
```

Then start (or restart) CS2.

## 3. Verify

Open the **Live GSI** view. Once you load into a match (or spectate a demo) the
status dot turns green and the fields populate in real time.

---

## Example config

[`gamestate_integration_ai_caster.example.cfg`](gamestate_integration_ai_caster.example.cfg)
is a reference copy. **Do not use it as-is** — it has a placeholder token. Always
generate your own so the auth token matches your installation.

## Notes

- The `auth.token` in the file must equal `gsi.auth_token` in the app settings,
  otherwise payloads are rejected (HTTP 401) unless auth is disabled.
- The app binds to `127.0.0.1` by default; CS2 posts to the same host/port.
- The `data` block requests every component the caster uses (map, round, player,
  all-players state/weapons/positions, bomb, phase countdowns).
