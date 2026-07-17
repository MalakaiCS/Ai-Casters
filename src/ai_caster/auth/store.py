"""Persistence for the current auth session ("remember me").

Stores the active session as JSON under the config directory so the operator
stays signed in across restarts — important for an unattended broadcast box.
Writes are atomic (temp-then-rename) like the settings manager. This is local
persistence, not a secrets vault; tokens live in the user's per-account config
directory with the rest of the app's state.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from ai_caster.auth.models import Account, AuthSession
from ai_caster.core.logging import get_logger

_log = get_logger("auth.store")


class SessionStore:
    """Loads/saves/clears the persisted :class:`AuthSession`."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> AuthSession | None:
        if not self._path.exists():
            return None
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            account = Account(
                user_id=str(data["account"]["user_id"]),
                email=str(data["account"].get("email", "")),
                display_name=str(data["account"].get("display_name", "")),
                tier=str(data["account"].get("tier", "free")),
                # Persist the RBAC role so a restored session (e.g. after an
                # auto-update restart) keeps the real role instead of defaulting to
                # "user" until the next manual sign-in.
                role=str(data["account"].get("role", "user")),
            )
            expires = data.get("expires_at")
            return AuthSession(
                account=account,
                access_token=str(data.get("access_token", "")),
                refresh_token=str(data.get("refresh_token", "")),
                expires_at=datetime.fromisoformat(expires) if expires else None,
            )
        except (json.JSONDecodeError, KeyError, ValueError, OSError) as exc:
            _log.warning("Ignoring unreadable saved session (%s).", exc)
            return None

    def save(self, session: AuthSession) -> None:
        payload = {
            "account": {
                "user_id": session.account.user_id,
                "email": session.account.email,
                "display_name": session.account.display_name,
                "tier": session.account.tier,
                "role": session.account.role,
            },
            "access_token": session.access_token,
            "refresh_token": session.refresh_token,
            "expires_at": session.expires_at.isoformat() if session.expires_at else None,
        }
        text = json.dumps(payload, indent=2)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self._path.parent, prefix=".session-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
            os.replace(tmp, self._path)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def clear(self) -> None:
        try:
            self._path.unlink(missing_ok=True)
        except OSError:
            _log.exception("Could not clear saved session")
