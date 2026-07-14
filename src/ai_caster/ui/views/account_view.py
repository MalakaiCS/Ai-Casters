"""Account, License & Updates view (Milestone 8).

Sign in/out, shows the resolved subscription tier and its entitlements, lists the
account's registered devices, and surfaces update status. Drives the live auth,
licensing and updater clients; state labels refresh from core events marshalled
onto the Qt thread.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ai_caster.auth.client import AuthClient
from ai_caster.licensing.client import LicensingClient
from ai_caster.updater.updater import AutoUpdater


class AccountView(QWidget):
    """Login, subscription/entitlements, devices and update status."""

    def __init__(self, auth: AuthClient, licensing: LicensingClient, updater: AutoUpdater) -> None:
        super().__init__()
        self._auth = auth
        self._licensing = licensing
        self._updater = updater

        root = QVBoxLayout(self)
        title = QLabel("Account, License & Updates")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        root.addWidget(title)

        root.addWidget(self._build_account_box())
        root.addWidget(self._build_license_box())
        root.addWidget(self._build_update_box())
        root.addStretch(1)

        self._refresh_account()
        self._refresh_license()

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #
    def _build_account_box(self) -> QGroupBox:
        box = QGroupBox("Account")
        layout = QVBoxLayout(box)

        self._status = QLabel()
        layout.addWidget(self._status)

        form = QHBoxLayout()
        self._email = QLineEdit()
        self._email.setPlaceholderText("email")
        self._password = QLineEdit()
        self._password.setPlaceholderText("password")
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._sign_in = QPushButton("Sign in")
        self._sign_in.clicked.connect(self._on_sign_in)
        self._sign_out = QPushButton("Sign out")
        self._sign_out.clicked.connect(self._on_sign_out)
        form.addWidget(self._email)
        form.addWidget(self._password)
        form.addWidget(self._sign_in)
        form.addWidget(self._sign_out)
        layout.addLayout(form)

        self._devices = QListWidget()
        self._devices.setStyleSheet("font-size: 12px;")
        layout.addWidget(QLabel("Registered devices:"))
        layout.addWidget(self._devices)
        return box

    def _build_license_box(self) -> QGroupBox:
        box = QGroupBox("Subscription")
        layout = QVBoxLayout(box)
        self._license_label = QLabel()
        self._license_label.setWordWrap(True)
        layout.addWidget(self._license_label)
        return box

    def _build_update_box(self) -> QGroupBox:
        box = QGroupBox("Updates")
        layout = QVBoxLayout(box)
        self._update_label = QLabel(f"Current version {self._updater.current_version}.")
        self._update_label.setWordWrap(True)
        check = QPushButton("Check for updates")
        check.clicked.connect(self._on_check_updates)
        layout.addWidget(self._update_label)
        layout.addWidget(check)
        return box

    # ------------------------------------------------------------------ #
    # Actions
    # ------------------------------------------------------------------ #
    def _on_sign_in(self) -> None:
        self._auth.login(self._email.text().strip(), self._password.text())
        self._password.clear()

    def _on_sign_out(self) -> None:
        self._auth.logout()
        self._licensing.clear()

    def _on_check_updates(self) -> None:
        check = self._updater.check()
        if check.available and check.update is not None:
            self._update_label.setText(
                f"Update available: {check.update.version} (current {check.current})."
            )
        else:
            self._update_label.setText(f"Up to date (version {check.current}).")

    # ------------------------------------------------------------------ #
    # Refresh helpers
    # ------------------------------------------------------------------ #
    def _refresh_account(self) -> None:
        account = self._auth.account
        if account is not None:
            self._status.setText(f"Signed in as {account.label}.")
            self._refresh_devices(account.user_id)
        else:
            self._status.setText("Not signed in (offline mode available).")
            self._devices.clear()

    def _refresh_devices(self, account_id: str) -> None:
        self._devices.clear()
        token = self._auth.session.access_token if self._auth.session else ""
        for device in self._licensing.list_devices(account_id, token=token):
            suffix = "  (this device)" if device.current else ""
            self._devices.addItem(f"{device.name or device.device_id}{suffix}")

    def _refresh_license(self) -> None:
        ent = self._licensing.entitlements
        features = ", ".join(sorted(f.value for f in ent.features)) or "none"
        self._license_label.setText(
            f"Tier: {ent.tier.value}  ·  status: {self._licensing.status.value}\n"
            f"Features: {features}\n"
            f"Max devices: {ent.max_devices}"
        )

    # ------------------------------------------------------------------ #
    # Slots (Qt thread)
    # ------------------------------------------------------------------ #
    def on_auth_state(self, authenticated: bool, account, detail: str) -> None:  # noqa: ANN001
        self._refresh_account()

    def on_license_state(self, status: str, tier: str, offline: bool) -> None:
        self._refresh_license()

    def on_update_available(self, info, current: str, latest: str, mandatory: bool) -> None:  # noqa: ANN001
        tag = "  (required)" if mandatory else ""
        self._update_label.setText(f"Update available: {latest} (current {current}){tag}.")
