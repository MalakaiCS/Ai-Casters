"""Voice, audio routing and OBS view (Milestone 7).

Surfaces the two independent voice channels — enable, mute, volume, and live
queue/spoken counters — plus a **voice configuration** panel (TTS engine,
ElevenLabs key/model and a distinct voice per channel) and the OBS integration
status. Controls drive the live :class:`VoiceEngine`; counters and OBS scene
refresh from core events marshalled onto the Qt thread.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ai_caster.config.manager import SettingsManager
from ai_caster.obs.integration import OBSIntegration
from ai_caster.voice.catalog import (
    CUSTOM_LABEL,
    ELEVENLABS_MODELS,
    ELEVENLABS_VOICES,
    TTS_ENGINES,
    elevenlabs_voice,
)
from ai_caster.voice.channel import VoiceChannel
from ai_caster.voice.engine import VoiceEngine


class _ChannelPanel(QGroupBox):
    """Controls and live counters for one voice channel."""

    def __init__(self, title: str, channel: VoiceChannel) -> None:
        super().__init__(title)
        self._channel = channel
        layout = QVBoxLayout(self)

        toggles = QHBoxLayout()
        self._enable = QCheckBox("Enabled")
        self._enable.setChecked(True)
        self._enable.toggled.connect(channel.set_enabled)
        self._mute = QCheckBox("Mute")
        self._mute.toggled.connect(channel.set_muted)
        toggles.addWidget(self._enable)
        toggles.addWidget(self._mute)
        toggles.addStretch(1)
        layout.addLayout(toggles)

        vol_row = QHBoxLayout()
        vol_row.addWidget(QLabel("Volume"))
        self._volume = QSlider(Qt.Orientation.Horizontal)
        self._volume.setRange(0, 100)
        self._volume.setValue(int(channel.dsp.volume * 100))
        self._volume.valueChanged.connect(lambda v: channel.set_volume(v / 100.0))
        vol_row.addWidget(self._volume, stretch=1)
        layout.addLayout(vol_row)

        self._counters = QLabel("spoken: 0    pending: 0")
        self._counters.setStyleSheet("color: #888;")
        layout.addWidget(self._counters)

    def refresh(self) -> None:
        self._counters.setText(
            f"spoken: {self._channel.spoken_count}    pending: {self._channel.pending()}"
        )


class _VoicePicker(QWidget):
    """A catalogue dropdown plus a custom-id field for one channel's voice."""

    def __init__(self, current_voice_id: str) -> None:
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self._combo = QComboBox()
        for option in ELEVENLABS_VOICES:
            self._combo.addItem(option.label, option.voice_id)
        self._combo.addItem(CUSTOM_LABEL, None)
        self._custom = QLineEdit()
        self._custom.setPlaceholderText("custom voice id")
        row.addWidget(self._combo, stretch=1)
        row.addWidget(self._custom, stretch=1)

        self._combo.currentIndexChanged.connect(self._sync_custom_visibility)
        self._select(current_voice_id)
        self._sync_custom_visibility()

    def _select(self, voice_id: str) -> None:
        if voice_id and elevenlabs_voice(voice_id) is None:
            self._combo.setCurrentIndex(self._combo.count() - 1)  # Custom…
            self._custom.setText(voice_id)
            return
        for i in range(self._combo.count()):
            if self._combo.itemData(i) == voice_id:
                self._combo.setCurrentIndex(i)
                return
        self._combo.setCurrentIndex(0)

    def _is_custom(self) -> bool:
        return self._combo.currentData() is None

    def _sync_custom_visibility(self) -> None:
        self._custom.setVisible(self._is_custom())

    def voice_id(self) -> str:
        if self._is_custom():
            return self._custom.text().strip()
        return str(self._combo.currentData() or "")


class _VoiceConfigPanel(QGroupBox):
    """Choose the TTS engine, ElevenLabs credentials and a voice per channel."""

    def __init__(self, voice: VoiceEngine, settings_manager: SettingsManager) -> None:
        super().__init__("Voice engine & voices")
        self._voice = voice
        self._settings = settings_manager
        vs = settings_manager.settings.voice

        form = QFormLayout(self)

        self._engine = QComboBox()
        for value, label in TTS_ENGINES:
            self._engine.addItem(label, value)
        self._select_data(self._engine, vs.tts_engine)
        self._engine.currentIndexChanged.connect(self._sync_engine_fields)
        form.addRow("Engine", self._engine)

        self._api_key = QLineEdit(vs.elevenlabs_api_key)
        self._api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key.setPlaceholderText("ElevenLabs API key (xi-api-key)")
        form.addRow("ElevenLabs key", self._api_key)

        self._model = QComboBox()
        for value, label in ELEVENLABS_MODELS:
            self._model.addItem(label, value)
        self._select_data(self._model, vs.elevenlabs_model)
        form.addRow("ElevenLabs model", self._model)

        self._pbp_voice = _VoicePicker(vs.play_by_play.voice_id)
        form.addRow("Play-by-play voice", self._pbp_voice)
        self._analyst_voice = _VoicePicker(vs.analyst.voice_id)
        form.addRow("Analyst voice", self._analyst_voice)

        self._apply = QPushButton("Apply voices")
        self._apply.clicked.connect(self._on_apply)
        form.addRow("", self._apply)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color: #888;")
        form.addRow("", self._status)

        self._sync_engine_fields()

    @staticmethod
    def _select_data(combo: QComboBox, value: str) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    def _is_elevenlabs(self) -> bool:
        return self._engine.currentData() == "elevenlabs"

    def _sync_engine_fields(self) -> None:
        on = self._is_elevenlabs()
        self._api_key.setEnabled(on)
        self._model.setEnabled(on)
        self._pbp_voice.setEnabled(on)
        self._analyst_voice.setEnabled(on)

    def _on_apply(self) -> None:
        engine = str(self._engine.currentData())
        pbp_id = self._pbp_voice.voice_id()
        analyst_id = self._analyst_voice.voice_id()

        current = self._settings.settings
        voice = current.voice.model_copy(
            update={
                "tts_engine": engine,
                "elevenlabs_api_key": self._api_key.text().strip(),
                "elevenlabs_model": str(self._model.currentData()),
                "play_by_play": current.voice.play_by_play.model_copy(update={"voice_id": pbp_id}),
                "analyst": current.voice.analyst.model_copy(update={"voice_id": analyst_id}),
            }
        )
        self._settings.update(current.model_copy(update={"voice": voice}), section="voice")

        # Per-channel voice ids apply live; engine/key changes need a restart
        # because the TTS backend is built once when the engine starts.
        self._voice.play_by_play.set_voice_id(pbp_id)
        self._voice.analyst.set_voice_id(analyst_id)
        self._status.setText(
            "Saved. Voice selections apply now; engine or API-key changes take "
            "effect after you restart the app."
        )


class VoiceView(QWidget):
    """Voice configuration, live voice-channel controls and OBS status."""

    def __init__(
        self, voice: VoiceEngine, obs: OBSIntegration, settings_manager: SettingsManager
    ) -> None:
        super().__init__()
        self._voice = voice
        self._obs = obs

        root = QVBoxLayout(self)
        title = QLabel("Voice, Audio & OBS")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        root.addWidget(title)
        note = QLabel(
            "Two completely independent voices, each with its own queue, volume, "
            "mute, broadcast latency and dynamics chain, plus a combined monitor mix."
        )
        note.setStyleSheet("color: #888;")
        note.setWordWrap(True)
        root.addWidget(note)

        root.addWidget(_VoiceConfigPanel(voice, settings_manager))

        columns = QHBoxLayout()
        self._pbp = _ChannelPanel("Play-by-Play", voice.play_by_play)
        self._analyst = _ChannelPanel("Analyst", voice.analyst)
        columns.addWidget(self._pbp)
        columns.addWidget(self._analyst)
        root.addLayout(columns)

        obs_box = QGroupBox("OBS Integration")
        obs_layout = QVBoxLayout(obs_box)
        self._obs_label = QLabel(self._obs_summary())
        self._obs_label.setWordWrap(True)
        obs_layout.addWidget(self._obs_label)
        root.addWidget(obs_box)
        root.addStretch(1)

    def _obs_summary(self, scene: str | None = None) -> str:
        controller = self._obs.controller
        connected = "connected" if controller.is_connected else "offline"
        current = scene or getattr(controller, "current_scene", None) or "—"
        return f"OBS: {connected}    current scene: {current}"

    # -- slots (Qt thread) ---------------------------------------------- #
    def on_commentary_line(self, line) -> None:  # noqa: ANN001 - Qt slot payload
        self._pbp.refresh()
        self._analyst.refresh()

    def on_replay_state(self, state, transition: str) -> None:  # noqa: ANN001 - Qt slot
        self._pbp.refresh()
        self._analyst.refresh()
        self._obs_label.setText(self._obs_summary())
