from pathlib import Path
from types import SimpleNamespace
import wave

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QUrl

from pitchstems.gui_transport import (
    TransportController,
    find_existing_midi_previews,
    loop_playback_start,
    reset_player_source,
    safe_qt_multimedia_call,
    start_player_source,
)
from pitchstems import gui_transport_flow
from pitchstems.gui_transport_flow import midi_preview_note_stems, midi_preview_stems_to_render
from pitchstems.pipeline_models import PipelineResult, StemResult


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


def test_update_transport_position_loops_selected_chord_range() -> None:
    window = _TransportWindow(position_ms=2050, loop_range=(1.0, 2.0))

    gui_transport_flow.update_transport_position(window)

    assert window.seeked_seconds == [1.0]
    assert window.positions == [1.0]


def test_midi_preview_stems_to_render_filters_unavailable_tracks(tmp_path: Path) -> None:
    result = _pipeline_result(tmp_path / "song.pitchstems", [])
    window = _PreviewWindow(
        tracks=["Bass", "Drums", "Piano", "Ready"],
        note_stems=["bass", "drums", "ready"],
        existing_previews={"Ready": tmp_path / "ready.wav"},
        running={"drums"},
    )

    assert midi_preview_stems_to_render(window, result, {"BASS", "drums", "piano", "ready"}) == ["Bass"]
    assert window.worker_checks == [
        (result.project_dir, "Bass"),
        (result.project_dir, "Drums"),
    ]


def test_midi_preview_stems_to_render_requires_project_notes(tmp_path: Path) -> None:
    result = _pipeline_result(tmp_path / "song.pitchstems", [])
    window = _PreviewWindow(tracks=["Bass"], note_stems=[])

    assert midi_preview_stems_to_render(window, result) == []

    window.editor_project = None

    assert midi_preview_stems_to_render(window, result) == []


def test_midi_preview_note_stems_normalizes_note_stem_names() -> None:
    notes = [
        SimpleNamespace(stem="Bass"),
        SimpleNamespace(stem="bass"),
        SimpleNamespace(stem="PIANO"),
    ]

    assert midi_preview_note_stems(notes) == {"bass", "piano"}


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


def test_prepare_players_reuses_players_for_same_result(monkeypatch, tmp_path: Path) -> None:
    players = []
    outputs = []

    def make_player(*_args):
        player = _FakePlayer()
        players.append(player)
        return player

    def make_output(*_args):
        output = _FakeAudioOutput()
        outputs.append(output)
        return output

    monkeypatch.setattr("pitchstems.gui_transport.QMediaPlayer", make_player)
    monkeypatch.setattr("pitchstems.gui_transport.QAudioOutput", make_output)
    result = _pipeline_result(
        tmp_path,
        [
            StemResult("bass", tmp_path / "bass.wav"),
            StemResult("piano", tmp_path / "piano.wav"),
        ],
    )
    controller = TransportController(
        None,
        _Logger(),
        {"bass": _FakeCheck(True, True), "piano": _FakeCheck(True, True)},
        {"bass": _FakeSlider(80, True), "piano": _FakeSlider(80, True)},
        {},
        {},
    )

    controller.prepare_players(result)
    first_players = dict(controller.track_players)
    controller.prepare_players(result)

    assert controller.track_players == first_players
    assert len(players) == 2
    assert len(outputs) == 2
    assert players[0].actions == [
        "setAudioOutput",
        f"setSource:{QUrl.fromLocalFile(str(tmp_path / 'bass.wav')).toString()}",
    ]
    assert players[1].actions == [
        "setAudioOutput",
        f"setSource:{QUrl.fromLocalFile(str(tmp_path / 'piano.wav')).toString()}",
    ]


def test_prepare_transport_players_does_not_render_missing_midi_previews(tmp_path: Path) -> None:
    result = _pipeline_result(tmp_path, [StemResult("bass", tmp_path / "bass.wav")])
    window = _PrepareTransportWindow()

    gui_transport_flow.prepare_transport_players(window, result)

    assert window.transport.prepared_results == [result]
    assert window.transport.prepared_midi_synths == [(window.editor_project.notes, window.editor_project.duration)]
    assert window.attached_previews == []
    assert window.started_midi_renders == []
    assert window.refreshed_mix


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

    def pause(self) -> None:
        self.actions.append("pause")

    def setAudioOutput(self, output) -> None:
        del output
        self.actions.append("setAudioOutput")

    def setSource(self, source: QUrl) -> None:
        self.actions.append(f"setSource:{source.toString()}")

    def play(self) -> None:
        self.actions.append("play")

    def position(self) -> int:
        return 0


class _PositionPlayer:
    def __init__(self, position_ms: int) -> None:
        self._position_ms = position_ms

    def position(self) -> int:
        return self._position_ms


class _TransportWindow:
    def __init__(self, position_ms: int, loop_range: tuple[float, float] | None) -> None:
        self.master = _PositionPlayer(position_ms)
        self._loop_range = loop_range
        self.seeked_seconds: list[float] = []
        self.positions: list[float] = []

    def transport_master_player(self):
        return self.master

    def resync_transport_players(self, _master=None) -> None:
        pass

    def loop_playback_range(self) -> tuple[float, float] | None:
        return self._loop_range

    def seek_audio_players(self, seconds: float) -> None:
        self.seeked_seconds.append(seconds)

    def set_editor_position_seconds(
        self,
        seconds: float,
        save: bool = True,
        seek_players: bool = True,
    ) -> None:
        del save, seek_players
        self.positions.append(seconds)


class _PreviewWindow:
    def __init__(
        self,
        tracks: list[str],
        note_stems: list[str],
        existing_previews: dict[str, Path] | None = None,
        running: set[str] | None = None,
    ) -> None:
        self.midi_preview_jobs = SimpleNamespace(closing=False)
        self.editor_project = SimpleNamespace(
            tracks=[SimpleNamespace(name=name) for name in tracks],
            notes=[SimpleNamespace(stem=stem) for stem in note_stems],
        )
        self.transport = SimpleNamespace(midi_preview_paths=existing_previews or {})
        self.running = {stem.lower() for stem in (running or set())}
        self.worker_checks: list[tuple[Path, str]] = []

    def _midi_preview_worker_running(self, project_dir: Path, stem_name: str) -> bool:
        self.worker_checks.append((project_dir, stem_name))
        return stem_name.lower() in self.running


class _PrepareTransport:
    def __init__(self) -> None:
        self.midi_preview_paths: dict[str, Path] = {}
        self.prepared_results: list[PipelineResult] = []
        self.prepared_midi_synths: list[tuple[list[object], float]] = []

    def prepare_players(self, result: PipelineResult) -> None:
        self.prepared_results.append(result)

    def prepare_midi_synth(self, notes: list[object], duration: float) -> None:
        self.prepared_midi_synths.append((notes, duration))


class _PrepareTransportWindow:
    def __init__(self) -> None:
        self.transport = _PrepareTransport()
        self.editor_project = SimpleNamespace(notes=[SimpleNamespace(stem="bass")], duration=12.0)
        self.track_midi_checks = {"bass": _FakeCheck(True, True)}
        self.activity_messages: list[str] = []
        self.attached_previews: list[dict[str, Path]] = []
        self.started_midi_renders: list[tuple[PipelineResult, set[str] | None]] = []
        self.refreshed_mix = False

    def set_activity_message(self, message: str) -> None:
        self.activity_messages.append(message)

    def pause_transport(self) -> None:
        pass

    def attach_midi_preview_players(self, previews: dict[str, Path], finish_activity: bool = True) -> None:
        del finish_activity
        self.attached_previews.append(previews)

    def start_midi_preview_render(
        self,
        result: PipelineResult,
        requested_stems: set[str] | None = None,
    ) -> None:
        self.started_midi_renders.append((result, requested_stems))

    def refresh_playback_mix(self) -> None:
        self.refreshed_mix = True


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
