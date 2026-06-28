from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from pitchstems.gui_project_flow import _reset_loaded_project_state, _reset_track_control_state, set_audio_path


class _StatusBar:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def showMessage(self, message: str, _timeout: int) -> None:
        self.messages.append(message)


class _DropZone:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.reset_count = 0

    def set_audio_file(self, path: Path) -> None:
        self.path = path

    def reset_prompt(self) -> None:
        self.path = None
        self.reset_count += 1


class _Window:
    def __init__(self, previous_path: Path) -> None:
        self.drop_zone = _DropZone(previous_path)
        self.logs: list[str] = []
        self.status = _StatusBar()
        self.reset_paths: list[Path] = []

    def append_log(self, message: str) -> None:
        self.logs.append(message)

    def statusBar(self) -> _StatusBar:
        return self.status

    def reset_stage_state(self, path: Path) -> None:
        self.reset_paths.append(path)


def test_set_audio_path_invalid_selection_clears_previous_audio_path(tmp_path: Path) -> None:
    previous = tmp_path / "previous.wav"
    invalid = tmp_path / "notes.txt"
    previous.write_bytes(b"RIFF")
    invalid.write_text("not audio", encoding="utf-8")
    window = _Window(previous)

    set_audio_path(window, invalid)

    assert window.drop_zone.path is None
    assert window.drop_zone.reset_count == 1
    assert window.reset_paths == []
    assert any("Unsupported audio file type" in message for message in window.logs)


def test_reset_loaded_project_state_clears_editor_domain_state() -> None:
    window = SimpleNamespace(
        current_result=object(),
        current_stems=[object()],
        current_input_stem="song",
        base_editor_project=object(),
        editor_project=object(),
        manual_chords=[object()],
        removed_chord_ranges=[(1.0, 2.0)],
        chord_note_overrides={"bass": object()},
        chord_note_filter_context=object(),
        current_chord_base_weights={"C": 1.0},
        current_harmony_context=object(),
        current_theory_analysis=object(),
        current_chord_gap_analysis=object(),
    )

    _reset_loaded_project_state(window)

    assert window.current_result is None
    assert window.current_stems == []
    assert window.current_input_stem is None
    assert window.base_editor_project is None
    assert window.editor_project is None
    assert window.manual_chords == []
    assert window.removed_chord_ranges == []
    assert window.chord_note_overrides == {}
    assert window.chord_note_filter_context is None
    assert window.current_chord_base_weights == {}
    assert window.current_harmony_context is None
    assert window.current_theory_analysis is None
    assert window.current_chord_gap_analysis is None


def test_reset_track_control_state_clears_transport_and_track_caches() -> None:
    clear_calls = []
    window = SimpleNamespace(
        rendering_midi_previews={"bass"},
        clear_transport_players=lambda: clear_calls.append("cleared"),
        track_audio_checks={"bass": object()},
        track_audio_sliders={"bass": object()},
        track_midi_checks={"bass": object()},
        track_midi_sliders={"bass": object()},
        track_analysis_checks={"bass": object()},
        track_control_panels={"bass": object()},
        track_control_detail_rows={"bass": object()},
        track_control_top_spacer=object(),
        track_control_bottom_spacer=object(),
        hidden_track_status="hidden",
    )

    _reset_track_control_state(window)

    assert window.rendering_midi_previews == set()
    assert clear_calls == ["cleared"]
    assert window.track_audio_checks == {}
    assert window.track_audio_sliders == {}
    assert window.track_midi_checks == {}
    assert window.track_midi_sliders == {}
    assert window.track_analysis_checks == {}
    assert window.track_control_panels == {}
    assert window.track_control_detail_rows == {}
    assert window.track_control_top_spacer is None
    assert window.track_control_bottom_spacer is None
    assert window.hidden_track_status is None
