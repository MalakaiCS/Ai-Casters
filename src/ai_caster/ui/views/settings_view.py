"""Settings editor view.

Milestone 1 provides a fully working editor for the GSI section (the settings
that matter for connecting CS2) plus a one-click CS2 config-file export. The
remaining sections are shown read-only so the operator can see the full
configuration surface; the complete per-section editors arrive with the full UI
in Milestone 9.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ai_caster.config.manager import SettingsManager
from ai_caster.gsi.cfg import build_gsi_config


class SettingsView(QWidget):
    """Edit persisted settings. Emits nothing; saves via the SettingsManager."""

    def __init__(self, settings_manager: SettingsManager) -> None:
        super().__init__()
        self._manager = settings_manager

        root = QVBoxLayout(self)

        # ---- GSI section (editable) ------------------------------------- #
        gsi_box = QGroupBox("GSI — CS2 Game State Integration")
        form = QFormLayout(gsi_box)
        self._host = QLineEdit()
        self._port = QSpinBox()
        self._port.setRange(1, 65535)
        self._token = QLineEdit()
        self._require_auth = QCheckBox("Reject payloads with an invalid token")
        form.addRow("Bind host:", self._host)
        form.addRow("Port:", self._port)
        form.addRow("Auth token:", self._token)
        form.addRow("", self._require_auth)
        root.addWidget(gsi_box)

        # ---- actions ---------------------------------------------------- #
        actions = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._on_save)
        export_btn = QPushButton("Export CS2 GSI config…")
        export_btn.clicked.connect(self._on_export)
        actions.addWidget(save_btn)
        actions.addWidget(export_btn)
        actions.addStretch(1)
        root.addLayout(actions)

        # ---- read-only overview of everything else ---------------------- #
        other_box = QGroupBox("All settings (read-only preview)")
        other_layout = QVBoxLayout(other_box)
        note = QLabel("Full per-section editors arrive in Milestone 9.")
        note.setStyleSheet("color: #888;")
        other_layout.addWidget(note)
        self._overview = QPlainTextEdit()
        self._overview.setReadOnly(True)
        self._overview.setStyleSheet("font-family: monospace; font-size: 12px;")
        other_layout.addWidget(self._overview)
        root.addWidget(other_box, stretch=1)

        self.reload()

    # ------------------------------------------------------------------ #
    def reload(self) -> None:
        """Populate widgets from the current settings."""
        settings = self._manager.settings
        self._host.setText(settings.gsi.host)
        self._port.setValue(settings.gsi.port)
        self._token.setText(settings.gsi.auth_token)
        self._require_auth.setChecked(settings.gsi.require_auth)
        self._overview.setPlainText(settings.model_dump_json(indent=2))

    def _on_save(self) -> None:
        settings = self._manager.settings.model_copy(deep=True)
        try:
            settings.gsi.host = self._host.text().strip() or "127.0.0.1"
            settings.gsi.port = self._port.value()
            settings.gsi.auth_token = self._token.text().strip()
            settings.gsi.require_auth = self._require_auth.isChecked()
        except Exception as exc:  # noqa: BLE001 - surface validation errors to the user
            QMessageBox.warning(self, "Invalid settings", str(exc))
            return
        self._manager.update(settings, section="gsi")
        self._overview.setPlainText(self._manager.settings.model_dump_json(indent=2))
        QMessageBox.information(
            self, "Saved", "Settings saved. GSI auth is applied to the running receiver."
        )

    def _on_export(self) -> None:
        gsi = self._manager.settings.gsi
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export CS2 GSI config",
            "gamestate_integration_ai_caster.cfg",
            "CS2 config (*.cfg)",
        )
        if not path:
            return
        text = build_gsi_config(host=gsi.host, port=gsi.port, auth_token=gsi.auth_token)
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", str(exc))
            return
        QMessageBox.information(
            self,
            "Exported",
            "Copy the file into:\n"
            ".../Counter-Strike Global Offensive/game/csgo/cfg/\n\nThen (re)start CS2.",
        )
