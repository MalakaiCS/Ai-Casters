"""Voice, audio routing and OBS view (Milestone 7).

Surfaces the two independent voice channels — enable, mute, volume, and live
queue/spoken counters — plus the OBS integration status (auto-switch state and
the current scene). Controls drive the live :class:`VoiceEngine` channels; the
counters and OBS scene refresh from core events marshalled onto the Qt thread.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ai_caster.obs.integration import OBSIntegration
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


class VoiceView(QWidget):
    """Live voice-channel controls plus OBS integration status."""

    def __init__(self, voice: VoiceEngine, obs: OBSIntegration) -> None:
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
