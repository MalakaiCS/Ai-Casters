"""In-app AI training view (Staff and above).

A role-gated front-end for the offline training pipeline (Module 18). Staff can
teach the AI *general* delivery from **authorized** sources — transcript folders
and recordings they own — and tune tone (excitement) and pacing (when to speak,
when to hold back). It keeps the same guardrails as the CLI: authorized +
consent-referenced sources only, transcript/timing only (no voice cloning),
generic roles, proper nouns excluded, and third-party platform links refused.

Analysis runs on a worker thread. The learned style *suggests* pacing for review;
tone/pacing changes are only written to settings when the operator saves them —
nothing reaches the live engine automatically.
"""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ai_caster.auth.client import AuthClient
from ai_caster.auth.roles import can_train, role_label
from ai_caster.config.manager import SettingsManager


class TrainingView(QWidget):
    """Teach the AI general style from authorized sources, and tune tone/pacing."""

    _analysis_done = Signal(object)  # -> (summary:str, suggested:dict) | Exception

    def __init__(self, auth: AuthClient, settings_manager: SettingsManager) -> None:
        super().__init__()
        self._auth = auth
        self._settings = settings_manager
        self._dirs: list[str] = []
        self._media: list[str] = []
        self._last_profile = None

        root = QVBoxLayout(self)
        title = QLabel("Train the AI")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        root.addWidget(title)

        policy = QLabel(
            "Offline analysis of AUTHORIZED sources only. Recordings are transcribed "
            "to text + timing (no voice is ever cloned), speakers are anonymized, and "
            "third-party platform links (YouTube/Twitch/etc.) are refused. Learned "
            "style only *suggests* settings for you to review."
        )
        policy.setWordWrap(True)
        policy.setStyleSheet("color: #888;")
        root.addWidget(policy)

        self._gate = QLabel("")
        self._gate.setWordWrap(True)
        self._gate.setStyleSheet("color: #888;")
        root.addWidget(self._gate)

        self._body = QWidget()
        body = QVBoxLayout(self._body)
        body.setContentsMargins(0, 0, 0, 0)
        body.addWidget(self._build_sources_box())
        body.addWidget(self._build_analysis_box())
        body.addWidget(self._build_tuning_box())
        root.addWidget(self._body, stretch=1)
        root.addStretch(0)

        self._analysis_done.connect(self._on_analysis_done)
        self._load_tuning()
        self._apply_gate()

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #
    def _build_sources_box(self) -> QGroupBox:
        box = QGroupBox("1 · Authorized sources")
        layout = QVBoxLayout(box)

        buttons = QHBoxLayout()
        add_dir = QPushButton("Add transcript folder…")
        add_dir.clicked.connect(self._add_dir)
        add_media = QPushButton("Add recording(s)…")
        add_media.clicked.connect(self._add_media)
        clear = QPushButton("Clear")
        clear.clicked.connect(self._clear_sources)
        buttons.addWidget(add_dir)
        buttons.addWidget(add_media)
        buttons.addWidget(clear)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        consent_row = QHBoxLayout()
        consent_row.addWidget(QLabel("Consent / rights reference"))
        self._consent = QLineEdit()
        self._consent.setPlaceholderText("required for recordings — e.g. OWN-RECORDING-2026-004")
        consent_row.addWidget(self._consent, stretch=1)
        layout.addLayout(consent_row)

        self._sources = QListWidget()
        layout.addWidget(self._sources)
        return box

    def _build_analysis_box(self) -> QGroupBox:
        box = QGroupBox("2 · Analyze")
        layout = QVBoxLayout(box)
        row = QHBoxLayout()
        self._analyze_btn = QPushButton("Analyze sources")
        self._analyze_btn.clicked.connect(self._on_analyze)
        self._save_profile_btn = QPushButton("Save style profile…")
        self._save_profile_btn.clicked.connect(self._save_profile)
        self._save_profile_btn.setEnabled(False)
        row.addWidget(self._analyze_btn)
        row.addWidget(self._save_profile_btn)
        row.addStretch(1)
        layout.addLayout(row)

        self._results = QPlainTextEdit()
        self._results.setReadOnly(True)
        self._results.setPlaceholderText("Analysis results appear here.")
        layout.addWidget(self._results)
        return box

    def _build_tuning_box(self) -> QGroupBox:
        box = QGroupBox("3 · Tone & pacing (when to be excited, when to hold back)")
        layout = QVBoxLayout(box)

        self._excite_label = QLabel()
        self._excitement = QSlider(Qt.Orientation.Horizontal)
        self._excitement.setRange(0, 100)
        self._excitement.valueChanged.connect(self._update_tuning_labels)
        layout.addWidget(self._excite_label)
        layout.addWidget(self._excitement)

        self._gap_label = QLabel()
        self._gap = QSlider(Qt.Orientation.Horizontal)
        self._gap.setRange(0, 3000)
        self._gap.setSingleStep(50)
        self._gap.valueChanged.connect(self._update_tuning_labels)
        layout.addWidget(self._gap_label)
        layout.addWidget(self._gap)

        self._interrupt = QCheckBox(
            "Allow the play-by-play to interrupt the analyst on big moments"
        )
        layout.addWidget(self._interrupt)

        row = QHBoxLayout()
        self._apply_suggested = QPushButton("Apply suggested pacing from analysis")
        self._apply_suggested.clicked.connect(self._apply_suggested_pacing)
        self._apply_suggested.setEnabled(False)
        self._save_tuning = QPushButton("Save tone & pacing")
        self._save_tuning.clicked.connect(self._save_tuning_settings)
        row.addWidget(self._apply_suggested)
        row.addWidget(self._save_tuning)
        row.addStretch(1)
        layout.addLayout(row)

        self._tuning_status = QLabel("")
        self._tuning_status.setStyleSheet("color: #888;")
        layout.addWidget(self._tuning_status)
        return box

    # ------------------------------------------------------------------ #
    # Gating
    # ------------------------------------------------------------------ #
    def _role(self):
        account = self._auth.account
        return account.role_enum if account is not None else None

    def _apply_gate(self) -> None:
        role = self._role()
        if role is None or not can_train(role):
            shown = role_label(role) if role is not None else "signed out"
            self._gate.setText(
                f"Training is available to Staff and above. Your role ({shown}) "
                "doesn't have access — ask an admin to grant it."
            )
            self._body.setVisible(False)
            return
        self._gate.setText(f"Signed in as {role_label(role)} — training enabled.")
        self._body.setVisible(True)

    def on_auth_state(self, authenticated: bool, account, detail: str) -> None:  # noqa: ANN001
        self._apply_gate()

    # ------------------------------------------------------------------ #
    # Sources
    # ------------------------------------------------------------------ #
    def _add_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose a transcript folder")
        if path:
            self._dirs.append(path)
            self._sources.addItem(f"[transcripts] {path}")

    def _add_media(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Choose authorized recordings",
            filter="Media (*.wav *.mp3 *.mp4 *.mkv *.m4a);;All files (*)",
        )
        for path in paths:
            self._media.append(path)
            self._sources.addItem(f"[recording] {path}")

    def _clear_sources(self) -> None:
        self._dirs.clear()
        self._media.clear()
        self._sources.clear()

    # ------------------------------------------------------------------ #
    # Analysis (worker thread)
    # ------------------------------------------------------------------ #
    def _on_analyze(self) -> None:
        if not self._dirs and not self._media:
            self._results.setPlainText("Add at least one transcript folder or recording first.")
            return
        if self._media and not self._consent.text().strip():
            self._results.setPlainText(
                "Recordings need a consent/rights reference (that you own or are "
                "licensed to use them). Enter one above."
            )
            return
        self._analyze_btn.setEnabled(False)
        self._results.setPlainText("Analyzing… (transcribing recordings can take a while)")
        args = (list(self._dirs), list(self._media), self._consent.text().strip())
        threading.Thread(target=self._run_analysis, args=args, name="train", daemon=True).start()

    def _run_analysis(self, dirs: list[str], media: list[str], consent: str) -> None:
        try:
            from ai_caster.training.models import Authorization
            from ai_caster.training.pipeline import TrainingPipeline

            pipeline = TrainingPipeline()
            for directory in dirs:
                pipeline.add_directory(Path(directory), skip_unauthorized=True)
            if media:
                from ai_caster.training.transcribe import WhisperTranscriber

                auth = Authorization(
                    authorized=True, consent_reference=consent, note="Added via in-app training."
                )
                transcriber = WhisperTranscriber()
                for item in media:
                    pipeline.add_media(item, authorization=auth, transcriber=transcriber)

            if not pipeline.sources:
                self._analysis_done.emit(
                    RuntimeError("No authorized sources were usable; nothing to analyze.")
                )
                return
            profile = pipeline.run()
            self._last_profile = profile
            summary = pipeline.summary(profile)
            suggested = pipeline.suggested_director_settings(profile)
            self._analysis_done.emit((summary, suggested))
        except Exception as exc:  # noqa: BLE001 - surfaced to the operator
            self._analysis_done.emit(exc)

    def _on_analysis_done(self, result) -> None:  # noqa: ANN001
        self._analyze_btn.setEnabled(True)
        if isinstance(result, Exception):
            self._results.setPlainText(f"Couldn't complete analysis:\n{result}")
            self._save_profile_btn.setEnabled(False)
            self._apply_suggested.setEnabled(False)
            return
        summary, suggested = result
        self._suggested = suggested
        gap = suggested.get("min_speech_gap_ms")
        self._results.setPlainText(
            f"{summary}\n\nSuggested (review before adopting): min speech gap {gap} ms."
        )
        self._save_profile_btn.setEnabled(True)
        self._apply_suggested.setEnabled(gap is not None)

    def _save_profile(self) -> None:
        if self._last_profile is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save style profile", "style-profile.json", "JSON (*.json)"
        )
        if not path:
            return
        from ai_caster.training.pipeline import TrainingPipeline

        TrainingPipeline.save_profile(self._last_profile, Path(path))
        self._results.appendPlainText(f"\nSaved profile to {path}")

    # ------------------------------------------------------------------ #
    # Tone & pacing
    # ------------------------------------------------------------------ #
    def _load_tuning(self) -> None:
        commentary = self._settings.settings.commentary
        self._excitement.setValue(int(round(commentary.excitement * 100)))
        self._gap.setValue(commentary.min_speech_gap_ms)
        self._interrupt.setChecked(commentary.allow_interruptions)
        self._update_tuning_labels()

    def _update_tuning_labels(self) -> None:
        self._excite_label.setText(f"Baseline excitement: {self._excitement.value()}%")
        self._gap_label.setText(
            f"Minimum gap between lines: {self._gap.value()} ms (higher = calmer, more selective)"
        )

    def _apply_suggested_pacing(self) -> None:
        gap = getattr(self, "_suggested", {}).get("min_speech_gap_ms")
        if gap is not None:
            self._gap.setValue(int(gap))
            self._tuning_status.setText("Applied suggested pacing — review, then Save.")

    def _save_tuning_settings(self) -> None:
        current = self._settings.settings
        commentary = current.commentary.model_copy(
            update={
                "excitement": self._excitement.value() / 100.0,
                "min_speech_gap_ms": self._gap.value(),
                "allow_interruptions": self._interrupt.isChecked(),
            }
        )
        self._settings.update(
            current.model_copy(update={"commentary": commentary}), section="commentary"
        )
        self._tuning_status.setText("Saved. Tone & pacing apply to new commentary.")
