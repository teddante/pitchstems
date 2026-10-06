from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QUrl

from pitchstems.gui_transport import (
    TransportController,
    loop_playback_start,
    reset_player_source,
    safe_qt_multimedia_call,
    start_player_source,
)
from pitchstems import gui_transport_flow
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


def test_prepare_transport_players_prepares_live_midi_synth(tmp_path: Path) -> None:
    result = _pipeline_result(tmp_path, [StemResult("bass", tmp_path / "bass.wav")])
    window = _PrepareTransportWindow()

    gui_transport_flow.prepare_transport_players(window, result)

    assert window.transport.prepared_results == [result]
    assert window.transport.prepared_midi_synths == [(window.editor_project.notes, window.editor_project.duration)]
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


def test_disabled_midi_controls_are_not_played(monkeypatch) -> None:
    monkeypatch.setattr("pitchstems.gui_transport.QMediaPlayer", _FakePlayer)
    monkeypatch.setattr("pitchstems.gui_transport.QAudioOutput", _FakeAudioOutput)
    midi_check = _FakeCheck(checked=True, enabled=False)
    midi_slider = _FakeSlider(value=70, enabled=False)
    controller = TransportController(None, _Logger(), {}, {}, {"piano": midi_check}, {"piano": midi_slider})

    assert controller.midi_track_volumes() == {}
    assert not controller.midi_track_enabled("piano")


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


class _PrepareTransport:
    def __init__(self) -> None:
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
        self.refreshed_mix = False

    def set_activity_message(self, message: str) -> None:
        self.activity_messages.append(message)

    def pause_transport(self) -> None:
        pass

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
