from __future__ import annotations

import threading

from PySide6.QtCore import QIODevice
from PySide6.QtMultimedia import QAudioFormat, QAudioSink

from pitchstems.editor_project import NoteEvent
from pitchstems.midi_synth import MidiSynthEngine


class MidiSynthIODevice(QIODevice):
    def __init__(self, engine: MidiSynthEngine, parent=None) -> None:
        super().__init__(parent)
        self.engine = engine
        self.position_seconds = 0.0
        self.track_volumes: dict[str, float] = {}
        self._lock = threading.Lock()

    def set_position(self, seconds: float) -> None:
        with self._lock:
            self.position_seconds = max(0.0, seconds)

    def set_track_volumes(self, volumes: dict[str, float]) -> None:
        with self._lock:
            self.track_volumes = dict(volumes)

    def current_position(self) -> float:
        with self._lock:
            return self.position_seconds

    def readData(self, maxlen: int) -> bytes:
        if maxlen <= 1:
            return b""
        frame_count = max(1, maxlen // 2)
        with self._lock:
            position = self.position_seconds
            volumes = dict(self.track_volumes)
            self.position_seconds += frame_count / self.engine.sample_rate
        return self.engine.render(position, frame_count, volumes)

    def writeData(self, data: bytes) -> int:
        del data
        return -1

    def bytesAvailable(self) -> int:
        return 8192 + super().bytesAvailable()

    def isSequential(self) -> bool:
        return True


class RealtimeMidiPreview:
    def __init__(self, parent, logger, sample_rate: int = 44_100) -> None:
        self.parent = parent
        self.logger = logger
        self.sample_rate = sample_rate
        self.engine: MidiSynthEngine | None = None
        self.device: MidiSynthIODevice | None = None
        self.sink: QAudioSink | None = None
        self.track_volumes: dict[str, float] = {}
        self.is_playing = False

    def set_notes(self, notes: list[NoteEvent], duration: float) -> None:
        self.stop()
        self.engine = MidiSynthEngine(notes, duration, self.sample_rate)
        self.device = MidiSynthIODevice(self.engine, self.parent) if self.engine.has_notes else None
        if self.device is not None:
            self.device.set_track_volumes(self.track_volumes)

    def set_track_volumes(self, volumes: dict[str, float]) -> None:
        self.track_volumes = dict(volumes)
        if self.device is not None:
            self.device.set_track_volumes(self.track_volumes)

    def play(self, position_seconds: float) -> None:
        if self.device is None:
            return
        try:
            self._ensure_sink()
            self.device.set_position(position_seconds)
            if not self.device.isOpen():
                self.device.open(QIODevice.OpenModeFlag.ReadOnly)
            assert self.sink is not None
            self.sink.start(self.device)
            self.is_playing = True
        except RuntimeError:
            self.logger.exception("Live MIDI preview start failed")

    def pause(self) -> None:
        if self.sink is not None:
            try:
                self.sink.stop()
            except RuntimeError:
                self.logger.exception("Live MIDI preview pause failed")
        self.is_playing = False

    def stop(self) -> None:
        self.pause()
        if self.device is not None:
            self.device.set_position(0.0)

    def seek(self, seconds: float) -> None:
        if self.device is not None:
            self.device.set_position(seconds)

    def resync(self, seconds: float, drift_seconds: float = 0.12) -> None:
        if not self.is_playing or self.device is None:
            return
        if abs(self.device.current_position() - seconds) > drift_seconds:
            self.device.set_position(seconds)

    def clear(self) -> None:
        self.stop()
        if self.sink is not None:
            try:
                self.sink.deleteLater()
            except RuntimeError:
                self.logger.exception("Live MIDI preview cleanup failed")
        self.sink = None
        self.device = None
        self.engine = None

    def _ensure_sink(self) -> None:
        if self.sink is not None:
            return
        audio_format = QAudioFormat()
        audio_format.setSampleRate(self.sample_rate)
        audio_format.setChannelCount(1)
        audio_format.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        self.sink = QAudioSink(audio_format, self.parent)
        self.sink.setVolume(1.0)
