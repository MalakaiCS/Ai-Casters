"""Account, License & Updates view (Milestone 8).

Sign in/out, shows the resolved subscription tier and its entitlements, lists the
account's registered devices, and surfaces update status. Drives the live auth,
licensing and updater clients; state labels refresh from core events marshalled
onto the Qt thread.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
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

    # Emitted from worker threads; delivered on the Qt thread.
    _update_result = Signal(object)  # -> UpdateCheck | Exception
    _install_result = Signal(object)  # -> Path | Exception

    def __init__(self, auth: AuthClient, licensing: LicensingClient, updater: AutoUpdater) -> None:
        super().__init__()
        self._auth = auth
        self._licensing = licensing
        self._updater = updater
        self._pending_update = None

        root = QVBoxLayout(self)
        title = QLabel("Account, License & Updates")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        root.addWidget(title)

        root.addWidget(self._build_account_box())
        root.addWidget(self._build_license_box())
        root.addWidget(self._build_update_box())
        root.addStretch(1)

        self._update_result.connect(self._apply_update_result)
        self._install_result.connect(self._apply_install_result)
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
        self._sign_up = QPushButton("Create account")
        self._sign_up.clicked.connect(self._on_sign_up)
        self._sign_out = QPushButton("Sign out")
        self._sign_out.clicked.connect(self._on_sign_out)
        form.addWidget(self._email)
        form.addWidget(self._password)
        form.addWidget(self._sign_in)
        form.addWidget(self._sign_up)
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

        buttons = QHBoxLayout()
        self._check_btn = QPushButton("Check for updates")
        self._check_btn.clicked.connect(self._on_check_updates)
        self._download_btn = QPushButton("Download && install")
        self._download_btn.clicked.connect(self._on_install)
        self._download_btn.setVisible(False)
        buttons.addWidget(self._check_btn)
        buttons.addWidget(self._download_btn)
        buttons.addStretch(1)

        layout.addWidget(self._update_label)
        layout.addLayout(buttons)
        return box

    # ------------------------------------------------------------------ #
    # Actions
    # ------------------------------------------------------------------ #
    def _on_sign_in(self) -> None:
        self._auth.login(self._email.text().strip(), self._password.text())
        self._password.clear()

    def _on_sign_up(self) -> None:
        result = self._auth.signup(self._email.text().strip(), self._password.text())
        self._password.clear()
        if result.ok and result.session is not None:
            return  # signed in; the auth-state signal refreshes the view
        if result.ok:
            self._status.setText("Account created — check your email to confirm, then sign in.")
        else:
            self._status.setText(result.error or "Sign-up failed.")

    def _on_sign_out(self) -> None:
        self._auth.logout()
        self._licensing.clear()

    def _on_check_updates(self) -> None:
        # Give immediate feedback and run the (network) check off the UI thread so
        # the window never freezes; the result comes back via _update_result.
        self._check_btn.setEnabled(False)
        self._download_btn.setVisible(False)
        self._update_label.setText("Checking for updates…")
        threading.Thread(target=self._run_update_check, name="update-check", daemon=True).start()

    def _run_update_check(self) -> None:
        try:
            result = self._updater.check()
        except Exception as exc:  # noqa: BLE001 - report failure instead of dying silently
            result = exc
        self._update_result.emit(result)

    def _on_install(self) -> None:
        update = self._pending_update
        if update is None or not update.url:
            return
        self._download_btn.setEnabled(False)
        self._check_btn.setEnabled(False)
        self._update_label.setText("Downloading update…")
        threading.Thread(
            target=self._run_install, args=(update,), name="update-install", daemon=True
        ).start()

    def _run_install(self, update) -> None:  # noqa: ANN001 - UpdateInfo
        try:
            self._updater.download_and_install(update)
            self._install_result.emit(True)
        except Exception as exc:  # noqa: BLE001 - report + offer the manual download
            self._install_result.emit(exc)

    def _apply_install_result(self, result) -> None:  # noqa: ANN001 - True | Exception
        if isinstance(result, Exception):
            self._download_btn.setEnabled(True)
            self._check_btn.setEnabled(True)
            self._update_label.setText("Download failed — opening the download page instead.")
            if self._pending_update is not None and self._pending_update.url:
                QDesktopServices.openUrl(QUrl(self._pending_update.url))
            return
        # Installer launched: close the app so it can replace the running files.
        self._update_label.setText("Installer launched — closing to apply the update…")
        QTimer.singleShot(1200, QApplication.quit)

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

    def _apply_update_result(self, result) -> None:  # noqa: ANN001 - UpdateCheck | Exception
        """Render the outcome of a manual check (runs on the Qt thread)."""
        self._check_btn.setEnabled(True)
        if isinstance(result, Exception):
            self._update_label.setText("Update check failed — please try again.")
            return
        if result.available and result.update is not None:
            self._pending_update = result.update
            self._update_label.setText(
                f"Update available: {result.update.version} (you have {result.current})."
            )
            self._download_btn.setVisible(True)
            return
        if result.latest is None:
            # Nothing came back: either no source is configured, or it was unreachable.
            if self._updater.updates_configured:
                self._update_label.setText("Couldn't reach the update server — try again later.")
            else:
                self._update_label.setText("Automatic updates aren't set up for this build.")
            return
        self._update_label.setText(f"You're on the latest version ({result.current}).")

    def on_update_available(self, info, current: str, latest: str, mandatory: bool) -> None:  # noqa: ANN001
        # Fired by the startup auto-check (via the event bridge).
        self._pending_update = info
        tag = "  (required)" if mandatory else ""
        self._update_label.setText(f"Update available: {latest} (you have {current}){tag}.")
        self._download_btn.setVisible(True)
