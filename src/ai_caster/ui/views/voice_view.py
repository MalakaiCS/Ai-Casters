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
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ai_caster.config.manager import SettingsManager
from ai_caster.obs.factory import create_obs_controller, obs_sdk_available
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
from ai_caster.voice.factory import create_default_output_sink, sound_output_available


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

        self._default_out = QPushButton("Play through default headset / speakers")
        self._default_out.setToolTip(
            "Route both casters and the monitor mix to your default Windows output "
            "device — no device names to configure."
        )
        self._default_out.clicked.connect(self._on_default_output)
        form.addRow("", self._default_out)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color: #888;")
        form.addRow("", self._status)

        self._sync_engine_fields()

    def _on_default_output(self) -> None:
        if not sound_output_available():
            self._status.setText(
                "Audio playback isn't available in this build (the sounddevice "
                "component is missing). Reinstall the latest version."
            )
            return
        rate = self._settings.settings.voice.sample_rate
        # Swap all three outputs to the OS default device, live.
        self._voice.play_by_play.set_sink(create_default_output_sink(rate, "play_by_play"))
        self._voice.analyst.set_sink(create_default_output_sink(rate, "analyst"))
        self._voice.monitor.set_sink(create_default_output_sink(rate, "monitor"))
        # Persist "default" so it sticks across restarts.
        current = self._settings.settings
        voice = current.voice.model_copy(
            update={
                "monitor_device": "default",
                "play_by_play": current.voice.play_by_play.model_copy(
                    update={"output_device": "default"}
                ),
                "analyst": current.voice.analyst.model_copy(update={"output_device": "default"}),
            }
        )
        self._settings.update(current.model_copy(update={"voice": voice}), section="voice")
        engine = self._settings.settings.voice.tts_engine
        hint = (
            " Tip: set the engine to ElevenLabs or System for real speech "
            "(Synthetic only plays a test tone)."
            if engine == "synthetic"
            else ""
        )
        self._status.setText("Now playing through your default output device." + hint)

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

        self._obs_panel = _OBSPanel(obs, settings_manager)
        root.addWidget(self._obs_panel)
        root.addStretch(1)

    # -- slots (Qt thread) ---------------------------------------------- #
    def on_commentary_line(self, line) -> None:  # noqa: ANN001 - Qt slot payload
        self._pbp.refresh()
        self._analyst.refresh()

    def on_replay_state(self, state, transition: str) -> None:  # noqa: ANN001 - Qt slot
        self._pbp.refresh()
        self._analyst.refresh()
        self._obs_panel.refresh_status()


class _OBSPanel(QGroupBox):
    """Connect to and control OBS: enable, credentials, connect/test, scenes.

    Replaces the old read-only status label. A user can now turn integration on,
    point it at their OBS WebSocket, connect, see the current scene and scene list,
    and choose which scenes to switch to for live/replay — all from the app.
    """

    def __init__(self, obs: OBSIntegration, settings_manager: SettingsManager) -> None:
        super().__init__("OBS Integration")
        self._obs = obs
        self._manager = settings_manager

        layout = QVBoxLayout(self)

        if not obs_sdk_available():
            warn = QLabel(
                "The OBS control library isn't available in this build, so OBS "
                "can't be reached. Reinstall the app to enable OBS integration."
            )
            warn.setWordWrap(True)
            warn.setStyleSheet("color: #cc6666;")
            layout.addWidget(warn)

        obs_settings = settings_manager.settings.audio_obs
        form = QFormLayout()
        self._enabled = QCheckBox("Enable OBS integration")
        self._enabled.setChecked(obs_settings.enabled)
        form.addRow("", self._enabled)

        self._host = QLineEdit(obs_settings.host)
        form.addRow("Host:", self._host)
        self._port = QSpinBox()
        self._port.setRange(1, 65535)
        self._port.setValue(obs_settings.port)
        form.addRow("Port:", self._port)
        self._password = QLineEdit(obs_settings.password)
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setPlaceholderText("From OBS → Tools → WebSocket Server Settings")
        form.addRow("Password:", self._password)

        self._auto_switch = QCheckBox("Auto-switch scenes on replay start/end")
        self._auto_switch.setChecked(obs_settings.auto_switch_scenes)
        form.addRow("", self._auto_switch)

        self._live_scene = QComboBox()
        self._live_scene.setEditable(True)
        self._replay_scene = QComboBox()
        self._replay_scene.setEditable(True)
        self._set_scene_options([obs_settings.live_scene, obs_settings.replay_scene])
        self._live_scene.setCurrentText(obs_settings.live_scene)
        self._replay_scene.setCurrentText(obs_settings.replay_scene)
        form.addRow("Live scene:", self._live_scene)
        form.addRow("Replay scene:", self._replay_scene)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        self._connect_btn = QPushButton("Connect")
        self._connect_btn.clicked.connect(self._on_connect)
        self._disconnect_btn = QPushButton("Disconnect")
        self._disconnect_btn.clicked.connect(self._on_disconnect)
        self._refresh_btn = QPushButton("Refresh scenes")
        self._refresh_btn.clicked.connect(self._on_refresh)
        self._save_btn = QPushButton("Save")
        self._save_btn.clicked.connect(self._on_save)
        for btn in (self._connect_btn, self._disconnect_btn, self._refresh_btn, self._save_btn):
            buttons.addWidget(btn)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self._status = QLabel()
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self.refresh_status()

    # -- helpers --------------------------------------------------------- #
    def _set_scene_options(self, scenes: list[str]) -> None:
        for combo in (self._live_scene, self._replay_scene):
            current = combo.currentText()
            combo.clear()
            for scene in dict.fromkeys(s for s in scenes if s):  # de-dupe, keep order
                combo.addItem(scene)
            if current:
                combo.setCurrentText(current)

    def _collect_settings(self):  # noqa: ANN202 - returns a copied AppSettings
        settings = self._manager.settings.model_copy(deep=True)
        obs = settings.audio_obs
        obs.enabled = self._enabled.isChecked()
        obs.host = self._host.text().strip() or "127.0.0.1"
        obs.port = self._port.value()
        obs.password = self._password.text()
        obs.auto_switch_scenes = self._auto_switch.isChecked()
        obs.live_scene = self._live_scene.currentText().strip() or "Live"
        obs.replay_scene = self._replay_scene.currentText().strip() or "Replay"
        return settings

    def _persist(self):  # noqa: ANN202
        settings = self._collect_settings()
        self._manager.update(settings, section="audio_obs")
        return settings.audio_obs

    # -- button handlers ------------------------------------------------- #
    def _on_save(self) -> None:
        obs = self._persist()
        self._obs.set_auto_switch(obs.auto_switch_scenes)
        self._obs.set_scenes(obs.live_scene, obs.replay_scene)
        self.refresh_status("Saved.")

    def _on_connect(self) -> None:
        obs = self._persist()
        if not obs.enabled:
            self.refresh_status("Enable OBS integration first, then Connect.")
            return
        controller = create_obs_controller(obs)
        self._obs.reconfigure(
            controller,
            auto_switch_scenes=obs.auto_switch_scenes,
            live_scene=obs.live_scene,
            replay_scene=obs.replay_scene,
        )
        try:
            controller.connect()
        except Exception as exc:  # noqa: BLE001 - surface the real connection error
            self.refresh_status(f"Could not connect: {exc}")
            QMessageBox.warning(
                self,
                "OBS connection failed",
                "Couldn't reach OBS. Check that OBS is open, its WebSocket server is "
                "enabled (Tools → WebSocket Server Settings), and the port/password "
                f"match.\n\n{exc}",
            )
            return
        self._load_scenes_from_obs()
        self.refresh_status("Connected.")

    def _on_disconnect(self) -> None:
        self._obs.disconnect()
        self.refresh_status("Disconnected.")

    def _on_refresh(self) -> None:
        if not self._obs.is_connected:
            self.refresh_status("Connect to OBS first.")
            return
        self._load_scenes_from_obs()
        self.refresh_status("Scenes refreshed.")

    def _load_scenes_from_obs(self) -> None:
        scenes = self._obs.scenes()
        if scenes:
            self._set_scene_options(scenes)

    # -- status ---------------------------------------------------------- #
    def refresh_status(self, note: str = "") -> None:
        connected = self._obs.is_connected
        current = self._obs.current_scene() or "—"
        state = "connected" if connected else "offline"
        colour = "#44cc66" if connected else "#cc9944"
        message = f"OBS: {state}    current scene: {current}"
        if note:
            message = f"{message}    ({note})"
        self._status.setText(message)
        self._status.setStyleSheet(f"color: {colour};")
        self._connect_btn.setEnabled(not connected)
        self._disconnect_btn.setEnabled(connected)
        self._refresh_btn.setEnabled(connected)
