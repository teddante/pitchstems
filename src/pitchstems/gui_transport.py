from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from pitchstems.pipeline import PipelineResult


class TransportController:
    def __init__(
        self,
        parent,
        logger,
        track_audio_checks: dict,
        track_audio_sliders: dict,
        track_midi_checks: dict,
        track_midi_sliders: dict,
    ) -> None:
        self.parent = parent
        self.logger = logger
        self.track_audio_checks = track_audio_checks
        self.track_audio_sliders = track_audio_sliders
        self.track_midi_checks = track_midi_checks
        self.track_midi_sliders = track_midi_sliders
        self.is_playing = False
        self.track_players: dict[str, QMediaPlayer] = {}
        self.track_audio_outputs: dict[str, QAudioOutput] = {}
        self.midi_players: dict[str, QMediaPlayer] = {}
        self.midi_audio_outputs: dict[str, QAudioOutput] = {}
        self.midi_preview_paths: dict[str, Path] = {}

    def prepare_players(self, result: PipelineResult) -> None:
        self.pause()
        self.clear_players()
        self.midi_preview_paths = find_existing_midi_previews(result)
        for stem in result.stems:
            player = QMediaPlayer(self.parent)
            output = QAudioOutput(self.parent)
            player.setAudioOutput(output)
            player.setSource(QUrl.fromLocalFile(str(stem.path)))
            self.track_players[stem.name] = player
            self.track_audio_outputs[stem.name] = output
        self.refresh_mix()

    def clear_players(self) -> None:
        for player in self.players():
            try:
                player.pause()
                player.setSource(QUrl())
                player.deleteLater()
            except RuntimeError:
                self.logger.exception("Transport player cleanup failed")
        for output in [*self.track_audio_outputs.values(), *self.midi_audio_outputs.values()]:
            output.deleteLater()
        self.track_players.clear()
        self.track_audio_outputs.clear()
        self.midi_players.clear()
        self.midi_audio_outputs.clear()
        self.midi_preview_paths.clear()
        self.is_playing = False

    def players(self) -> list[QMediaPlayer]:
        return list(self.track_players.values()) + list(self.midi_players.values())

    def attach_midi_preview_players(
        self,
        previews: dict[str, Path],
        position_seconds: float,
    ) -> int:
        self.midi_preview_paths.update(previews)
        attached = 0
        for stem_name, midi_preview in previews.items():
            if stem_name in self.midi_players:
                continue
            midi_player = QMediaPlayer(self.parent)
            midi_output = QAudioOutput(self.parent)
            midi_player.setAudioOutput(midi_output)
            midi_player.setSource(QUrl.fromLocalFile(str(midi_preview)))
            self.midi_players[stem_name] = midi_player
            self.midi_audio_outputs[stem_name] = midi_output
            attached += 1

            midi_check = self.track_midi_checks.get(stem_name)
            midi_slider = self.track_midi_sliders.get(stem_name)
            if midi_check:
                midi_check.setEnabled(True)
                midi_check.setToolTip(
                    "Play the generated MIDI preview audio for this stem. This does not affect chord detection."
                )
            if midi_slider:
                midi_slider.setEnabled(True)
                midi_slider.setToolTip("MIDI preview audio volume.")
            if self.is_playing and self.midi_track_enabled(stem_name):
                midi_player.setPosition(int(position_seconds * 1000))
                midi_player.play()
            else:
                midi_player.pause()
        self.refresh_mix()
        return attached

    def refresh_mix(self) -> None:
        for stem_name, output in self.track_audio_outputs.items():
            enabled = self.track_audio_checks.get(stem_name)
            slider = self.track_audio_sliders.get(stem_name)
            is_enabled = enabled.isChecked() if enabled else True
            volume = slider.value() / 100 if slider else 0.8
            output.setVolume(volume if is_enabled else 0.0)
        for stem_name, output in self.midi_audio_outputs.items():
            slider = self.track_midi_sliders.get(stem_name)
            volume = slider.value() / 100 if slider else 0.7
            output.setVolume(volume if self.midi_track_enabled(stem_name) else 0.0)

    def midi_track_enabled(self, stem_name: str) -> bool:
        checkbox = self.track_midi_checks.get(stem_name)
        return bool(checkbox and checkbox.isEnabled() and checkbox.isChecked())

    def apply_midi_transport_state(self, position_seconds: float) -> None:
        if not self.is_playing:
            return
        position_ms = int(position_seconds * 1000)
        for stem_name, player in self.midi_players.items():
            try:
                if self.midi_track_enabled(stem_name):
                    if player.playbackState() != QMediaPlayer.PlayingState:
                        player.setPosition(position_ms)
                        player.play()
                else:
                    player.pause()
            except RuntimeError:
                self.logger.exception("MIDI transport state update failed")

    def play(self, start_position: float) -> None:
        position_ms = int(start_position * 1000)
        for player in self.track_players.values():
            player.setPosition(position_ms)
            player.play()
        for stem_name, player in self.midi_players.items():
            player.setPosition(position_ms)
            if self.midi_track_enabled(stem_name):
                player.play()
            else:
                player.pause()
        self.is_playing = True

    def pause(self) -> bool:
        if not self.is_playing:
            return False
        for player in self.players():
            player.pause()
        self.is_playing = False
        return True

    def stop(self) -> None:
        self.is_playing = False
        for player in self.players():
            try:
                player.pause()
                player.setPosition(0)
            except RuntimeError:
                self.logger.exception("Transport stop failed")

    def seek(self, seconds: float) -> None:
        if not self.track_players:
            return
        position_ms = int(seconds * 1000)
        for player in self.players():
            player.setPosition(position_ms)

    def master_player(self) -> QMediaPlayer | None:
        return next(iter(self.track_players.values()), None)

    def resync(self, master: QMediaPlayer | None = None, drift_ms: int = 120) -> None:
        if not self.is_playing:
            return
        master = master or self.master_player()
        if master is None:
            return
        master_position = master.position()
        for player in self.players():
            if player is master:
                continue
            try:
                if player.playbackState() != QMediaPlayer.PlayingState:
                    continue
                if abs(player.position() - master_position) > drift_ms:
                    player.setPosition(master_position)
            except RuntimeError:
                self.logger.exception("Transport resync failed")


def find_existing_midi_previews(result: PipelineResult) -> dict[str, Path]:
    preview_dir = result.project_dir / "editor" / "midi-preview"
    previews = {}
    for stem in result.stems:
        preview = preview_dir / f"{stem.name}_midi_preview.wav"
        if preview.exists():
            previews[stem.name] = preview
    return previews


def loop_playback_start(position: float, selection: tuple[float, float] | None) -> float:
    if selection is None:
        return position
    start, end = selection
    if start <= position < end:
        return position
    return start
