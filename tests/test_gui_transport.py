from pathlib import Path
import wave

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QUrl  # noqa: E402

from pitchstems.gui_transport import (  # noqa: E402
    TransportController,
    find_existing_midi_previews,
    loop_playback_start,
    reset_player_source,
    safe_qt_multimedia_call,
    start_player_source,
)
from pitchstems.pipeline import PipelineResult  # noqa: E402
from pitchstems.separation import StemResult  # noqa: E402


def _pipeline_result(project_dir: Path, stems: list[StemResult]) -> PipelineResult:
    return PipelineResult(
        project_dir=project_dir,
        normalized_audio=project_dir / "audio.wav",
        stems=stems,
        midi_files=[],
        combined_midi=None,
        zip_path=None,
    )


def test_loop_playback_start_returns_position_without_selection() -> None:
    assert loop_playback_start(12.5, None) == 12.5


def test_loop_playback_start_keeps_position_inside_selection() -> None:
    assert loop_playback_start(12.5, (10.0, 15.0)) == 12.5


def test_loop_playback_start_jumps_to_selection_start_outside_selection() -> None:
    assert loop_playback_start(8.0, (10.0, 15.0)) == 10.0
    assert loop_playback_start(15.0, (10.0, 15.0)) == 10.0


def test_find_existing_midi_previews_returns_existing_stem_previews(tmp_path: Path) -> None:
    preview_dir = tmp_path / "editor" / "midi-preview"
    preview_dir.mkdir(parents=True)
    bass_preview = preview_dir / "bass_midi_preview.wav"
    _write_wav(bass_preview)
    result = _pipeline_result(
        tmp_path,
        [
            StemResult("bass", tmp_path / "bass.wav"),
            StemResult("piano", tmp_path / "piano.wav"),
        ],
    )

    assert find_existing_midi_previews(result) == {"bass": bass_preview}


def test_find_existing_midi_previews_uses_sanitized_stem_names(tmp_path: Path) -> None:
    preview_dir = tmp_path / "editor" / "midi-preview"
    preview_dir.mkdir(parents=True)
    preview = preview_dir / "bad_stem_midi_preview.wav"
    _write_wav(preview)
    result = _pipeline_result(tmp_path, [StemResult("../bad/stem", tmp_path / "bad.wav")])

    assert find_existing_midi_previews(result) == {"../bad/stem": preview}


def test_find_existing_midi_previews_ignores_unreadable_wavs(tmp_path: Path) -> None:
    preview_dir = tmp_path / "editor" / "midi-preview"
    preview_dir.mkdir(parents=True)
    bass_preview = preview_dir / "bass_midi_preview.wav"
    bass_preview.write_bytes(b"not a wav")
    result = _pipeline_result(tmp_path, [StemResult("bass", tmp_path / "bass.wav")])

    assert find_existing_midi_previews(result) == {}


def test_safe_qt_multimedia_call_reports_deleted_qt_objects() -> None:
    logger = _Logger()

    def fail() -> None:
        raise RuntimeError("wrapped C/C++ object has been deleted")

    assert not safe_qt_multimedia_call(logger, "cleanup failed", fail)
    assert logger.messages == ["cleanup failed"]


def test_safe_qt_multimedia_call_returns_true_when_operation_succeeds() -> None:
    logger = _Logger()
    calls = []

    assert safe_qt_multimedia_call(logger, "cleanup failed", lambda: calls.append("ok"))
    assert calls == ["ok"]
    assert logger.messages == []


def test_reset_player_source_pauses_and_clears_source() -> None:
    player = _FakePlayer()

    reset_player_source(player)

    assert player.actions == ["pause", "setSource:"]


def test_start_player_source_sets_source_and_plays() -> None:
    player = _FakePlayer()

    start_player_source(player, QUrl("file:///preview.wav"))

    assert player.actions == ["setSource:file:///preview.wav", "play"]


def test_attach_midi_preview_players_preserves_disabled_controls(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("pitchstems.gui_transport.QMediaPlayer", _FakePlayer)
    monkeypatch.setattr("pitchstems.gui_transport.QAudioOutput", _FakeAudioOutput)
    midi_check = _FakeCheck(checked=True, enabled=False)
    midi_slider = _FakeSlider(value=70, enabled=False)
    controller = TransportController(None, _Logger(), {}, {}, {"piano": midi_check}, {"piano": midi_slider})
    preview = tmp_path / "piano_midi_preview.wav"
    _write_wav(preview)

    assert controller.attach_midi_preview_players({"piano": preview}, 12.0) == 1

    assert not midi_check.enabled
    assert not midi_slider.enabled
    assert "generated MIDI preview audio" in midi_check.tooltip
    assert midi_slider.tooltip == "MIDI preview audio volume."
    assert not controller.midi_track_enabled("piano")


def _write_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x00\x00" * 16)


class _Logger:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def exception(self, message: str) -> None:
        self.messages.append(message)


class _FakePlayer:
    def __init__(self, *_args) -> None:
        self.actions: list[str] = []
        self.audio_output = None

    def pause(self) -> None:
        self.actions.append("pause")

    def setAudioOutput(self, output) -> None:
        self.audio_output = output
        self.actions.append("setAudioOutput")

    def setSource(self, source: QUrl) -> None:
        self.actions.append(f"setSource:{source.toString()}")

    def play(self) -> None:
        self.actions.append("play")


class _FakeAudioOutput:
    def __init__(self, *_args) -> None:
        self.volume = 0.0

    def setVolume(self, volume: float) -> None:
        self.volume = volume

    def deleteLater(self) -> None:
        pass


class _FakeCheck:
    def __init__(self, checked: bool, enabled: bool) -> None:
        self.checked = checked
        self.enabled = enabled
        self.tooltip = ""

    def isChecked(self) -> bool:
        return self.checked

    def isEnabled(self) -> bool:
        return self.enabled

    def setEnabled(self, enabled: bool) -> None:
        self.enabled = enabled

    def setToolTip(self, tooltip: str) -> None:
        self.tooltip = tooltip


class _FakeSlider:
    def __init__(self, value: int, enabled: bool) -> None:
        self._value = value
        self.enabled = enabled
        self.tooltip = ""

    def value(self) -> int:
        return self._value

    def setEnabled(self, enabled: bool) -> None:
        self.enabled = enabled

    def setToolTip(self, tooltip: str) -> None:
        self.tooltip = tooltip
