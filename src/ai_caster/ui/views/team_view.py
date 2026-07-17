"""Team & Roles admin view (Admin and above).

Lists everyone on the account and lets a manager change a member's role. The
actual authority is server-side: the ``set_user_role`` RPC re-checks the caller's
role, and a manager may only assign roles strictly below their own — this view
just mirrors that so the UI never offers an action the server would reject.

For non-managers (or a build without the cloud account service) the view shows a
short explanation instead of the roster.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ai_caster.auth.client import AuthClient
from ai_caster.auth.durations import DURATION_PRESETS
from ai_caster.auth.roles import Role, assignable_roles, can_manage_roles, role_label
from ai_caster.auth.team import TeamClient, TeamMember
from ai_caster.licensing.models import SubscriptionTier


class TeamView(QWidget):
    """View and change team members' roles (permission-gated)."""

    _members_ready = Signal(object)  # -> list[TeamMember] | Exception
    _set_done = Signal(object)  # -> str (message)
    _tier_done = Signal(object)  # -> str (message)

    def __init__(self, auth: AuthClient, team: TeamClient) -> None:
        super().__init__()
        self._auth = auth
        self._team = team
        self._members: list[TeamMember] = []

        root = QVBoxLayout(self)
        title = QLabel("Team & Roles")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        root.addWidget(title)

        self._gate = QLabel("")
        self._gate.setWordWrap(True)
        self._gate.setStyleSheet("color: #888;")
        root.addWidget(self._gate)

        self._body = QWidget()
        body = QHBoxLayout(self._body)
        body.setContentsMargins(0, 0, 0, 0)

        left = QVBoxLayout()
        self._refresh_btn = QPushButton("Refresh roster")
        self._refresh_btn.clicked.connect(self._load_members)
        left.addWidget(self._refresh_btn)
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_select)
        left.addWidget(self._list, stretch=1)
        body.addLayout(left, stretch=1)

        right = QVBoxLayout()

        # --- role ------------------------------------------------------- #
        edit = QGroupBox("Change role")
        edit_layout = QVBoxLayout(edit)
        self._who = QLabel("Select a member.")
        self._who.setWordWrap(True)
        edit_layout.addWidget(self._who)
        role_row = QHBoxLayout()
        role_row.addWidget(QLabel("Role"))
        self._role_combo = QComboBox()
        role_row.addWidget(self._role_combo, stretch=1)
        edit_layout.addLayout(role_row)
        self._apply_btn = QPushButton("Update role")
        self._apply_btn.clicked.connect(self._on_apply)
        self._apply_btn.setEnabled(False)
        edit_layout.addWidget(self._apply_btn)
        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color: #888;")
        edit_layout.addWidget(self._status)
        right.addWidget(edit)

        # --- subscription tier ----------------------------------------- #
        sub = QGroupBox("Subscription")
        sub_layout = QVBoxLayout(sub)
        tier_row = QHBoxLayout()
        tier_row.addWidget(QLabel("Tier"))
        self._tier_combo = QComboBox()
        for tier in SubscriptionTier:
            self._tier_combo.addItem(tier.value, tier.value)
        tier_row.addWidget(self._tier_combo, stretch=1)
        sub_layout.addLayout(tier_row)
        dur_row = QHBoxLayout()
        dur_row.addWidget(QLabel("Duration"))
        self._duration_combo = QComboBox()
        for preset in DURATION_PRESETS:
            self._duration_combo.addItem(preset.label, preset.days)
        self._duration_combo.setCurrentText("30 days")
        dur_row.addWidget(self._duration_combo, stretch=1)
        sub_layout.addLayout(dur_row)
        self._tier_btn = QPushButton("Update subscription")
        self._tier_btn.clicked.connect(self._on_apply_tier)
        self._tier_btn.setEnabled(False)
        sub_layout.addWidget(self._tier_btn)
        self._tier_status = QLabel("")
        self._tier_status.setWordWrap(True)
        self._tier_status.setStyleSheet("color: #888;")
        sub_layout.addWidget(self._tier_status)
        right.addWidget(sub)
        right.addStretch(1)

        body.addLayout(right, stretch=1)

        root.addWidget(self._body, stretch=1)
        root.addStretch(0)

        self._members_ready.connect(self._on_members_ready)
        self._set_done.connect(self._on_set_done)
        self._tier_done.connect(self._on_tier_done)
        self._apply_gate()

    # ------------------------------------------------------------------ #
    def _current_role(self) -> Role:
        account = self._auth.account
        return account.role_enum if account is not None else Role.USER

    def _apply_gate(self) -> None:
        """Show or hide the roster based on the current user's role."""
        role = self._current_role()
        if not self._team.supported:
            self._gate.setText(
                "Team management is available when the app is signed in to the cloud "
                "account service."
            )
            self._body.setVisible(False)
            return
        if not can_manage_roles(role):
            self._gate.setText(
                f"Your role ({role_label(role)}) can't manage the team. "
                "Admins and above can view and change roles."
            )
            self._body.setVisible(False)
            return
        self._gate.setText(f"Signed in as {role_label(role)}. You can assign roles below your own.")
        self._body.setVisible(True)
        if not self._members:
            self._load_members()

    # ------------------------------------------------------------------ #
    def _load_members(self) -> None:
        if not self._team.supported or not can_manage_roles(self._current_role()):
            return
        self._refresh_btn.setEnabled(False)
        self._status.setText("Loading roster…")
        token = self._auth.session.access_token if self._auth.session else ""
        threading.Thread(
            target=self._run_load, args=(token,), name="team-load", daemon=True
        ).start()

    def _run_load(self, token: str) -> None:
        try:
            members = self._team.list_members(token=token)
            self._members_ready.emit(members)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user
            self._members_ready.emit(exc)

    def _on_members_ready(self, result) -> None:  # noqa: ANN001
        self._refresh_btn.setEnabled(True)
        if isinstance(result, Exception):
            self._status.setText("Couldn't load the roster — try again.")
            return
        self._members = list(result)
        self._list.clear()
        for member in self._members:
            self._list.addItem(member.label)
        self._status.setText(f"{len(self._members)} member(s).")

    # ------------------------------------------------------------------ #
    def _on_select(self, row: int) -> None:
        if row < 0 or row >= len(self._members):
            self._apply_btn.setEnabled(False)
            self._who.setText("Select a member.")
            self._role_combo.clear()
            return
        member = self._members[row]
        self._who.setText(
            f"{member.email}\nCurrent role: {role_label(member.role_enum)}"
            f"\nSubscription: {member.tier_summary}"
        )
        self._role_combo.clear()
        for role in assignable_roles(self._current_role()):
            self._role_combo.addItem(role_label(role), role.value)
        # Role changes are self-blocked (no changing your own rank), but a
        # subscription is a grant, not a rank — a manager can set anyone's tier,
        # including their own account.
        role_editable = member.user_id != self._self_id()
        self._apply_btn.setEnabled(role_editable and self._role_combo.count() > 0)
        if not role_editable:
            self._status.setText("You can't change your own role.")
        else:
            self._status.setText("")

        self._tier_btn.setEnabled(True)
        self._select_combo_data(self._tier_combo, member.tier)
        self._tier_status.setText("")

    def _self_id(self) -> str:
        account = self._auth.account
        return account.user_id if account is not None else ""

    def _on_apply(self) -> None:
        row = self._list.currentRow()
        if row < 0 or row >= len(self._members):
            return
        member = self._members[row]
        role = str(self._role_combo.currentData() or "")
        if not role:
            return
        self._apply_btn.setEnabled(False)
        self._status.setText(f"Setting {member.email} to {role}…")
        token = self._auth.session.access_token if self._auth.session else ""
        threading.Thread(
            target=self._run_set,
            args=(member.user_id, role, token),
            name="team-set",
            daemon=True,
        ).start()

    def _run_set(self, user_id: str, role: str, token: str) -> None:
        result = self._team.set_role(user_id, role, token=token)
        self._set_done.emit(result.error if not result.ok else "")

    def _on_set_done(self, error: str) -> None:
        self._apply_btn.setEnabled(True)
        if error:
            self._status.setText(error)
            return
        self._status.setText("Role updated.")
        self._load_members()

    # -- tier ----------------------------------------------------------- #
    @staticmethod
    def _select_combo_data(combo: QComboBox, value: str) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    def _on_apply_tier(self) -> None:
        from datetime import UTC, datetime, timedelta

        row = self._list.currentRow()
        if row < 0 or row >= len(self._members):
            return
        member = self._members[row]
        tier = str(self._tier_combo.currentData() or "free")
        days = self._duration_combo.currentData()  # int | None (None = lifetime)
        expires_at = (
            None if days is None else (datetime.now(UTC) + timedelta(days=int(days))).isoformat()
        )
        self._tier_btn.setEnabled(False)
        window = "lifetime" if days is None else f"{days} day(s)"
        self._tier_status.setText(f"Setting {member.email} to {tier} for {window}…")
        token = self._auth.session.access_token if self._auth.session else ""
        threading.Thread(
            target=self._run_set_tier,
            args=(member.user_id, tier, expires_at, token),
            name="team-tier",
            daemon=True,
        ).start()

    def _run_set_tier(self, user_id: str, tier: str, expires_at, token: str) -> None:  # noqa: ANN001
        result = self._team.set_tier(user_id, tier, expires_at, token=token)
        self._tier_done.emit(result.error if not result.ok else "")

    def _on_tier_done(self, error: str) -> None:
        self._tier_btn.setEnabled(True)
        if error:
            self._tier_status.setText(error)
            return
        self._tier_status.setText("Subscription updated.")
        self._load_members()

    # ------------------------------------------------------------------ #
    # Slots (Qt thread)
    # ------------------------------------------------------------------ #
    def on_auth_state(self, authenticated: bool, account, detail: str) -> None:  # noqa: ANN001
        self._members = []
        self._list.clear()
        self._apply_gate()
