import queue
from pathlib import Path
from types import SimpleNamespace

import pytest


pytest.importorskip("PySide6")

from PySide6.QtCore import Qt

from pitchstems import gui_editor_state
from pitchstems.editor_models import ChordRegion
from pitchstems.editor_project import EditorProject
from pitchstems.gui_editor_state import EditorLayoutPolicy, EditorSummaryModel


def test_editor_summary_model_empty_project() -> None:
    model = EditorSummaryModel(track_count=0, note_count=0, duration_seconds=0.0)

    assert model.has_timeline is False
    assert model.fit_song_enabled is False
    assert model.summary == "Run separation + MIDI to build an editor timeline."


def test_editor_summary_model_loaded_project() -> None:
    model = EditorSummaryModel(track_count=2, note_count=150, duration_seconds=92.4)

    assert model.has_timeline is True
    assert model.fit_song_enabled is True
    assert "2 tracks" in model.summary
    assert "150 notes" in model.summary


def test_editor_layout_policy_uses_compact_panels_below_desktop_width() -> None:
    policy = EditorLayoutPolicy(window_width=900)

    assert policy.compact is True
    assert policy.harmony_panel_min_width == 260
    assert policy.harmony_panel_width == 360
    assert policy.track_panel_min_width == 220
    assert policy.track_panel_width == 250


def test_editor_layout_policy_uses_roomier_panels_on_default_window() -> None:
    policy = EditorLayoutPolicy(window_width=1220)

    assert policy.compact is False
    assert policy.harmony_panel_min_width == 300
    assert policy.harmony_panel_width == 440
    assert policy.track_panel_min_width == 250
    assert policy.track_panel_width == 280


class _Item:
    def data(self, role: int):
        if role == Qt.UserRole:
            return "C"
        if role == Qt.UserRole + 1:
            return 0.72
        return None


class _ChordList:
    def currentItem(self):
        return _Item()


class _Timeline:
    def __init__(self, selected_chord: ChordRegion | None = None) -> None:
        self.selected_chord = selected_chord

    def selection_ranges(self) -> list[tuple[float, float]]:
        return []


class _StatusBar:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def showMessage(self, message: str, _timeout: int) -> None:
        self.messages.append(message)


class _Window:
    def __init__(self) -> None:
        self.editor_project = object()
        self.current_result = object()
        self.timeline = _Timeline(ChordRegion(1.0, 2.0, "G", 0.8))
        self.chord_list = _ChordList()
        self.manual_chords: list[ChordRegion] = []
        self.removed_chord_ranges: list[tuple[float, float]] = []
        self.refreshed_with: ChordRegion | None = None
        self.status = _StatusBar()

    def insert_manual_chord(self, chord: ChordRegion) -> None:
        gui_editor_state.insert_manual_chord(self, chord)

    def refresh_editor_project_from_chord_edits(self, selected_chord: ChordRegion | None = None) -> None:
        self.refreshed_with = selected_chord

    def display_chord(self, label: str) -> str:
        return label

    def statusBar(self) -> _StatusBar:
        return self.status


def test_assign_selected_chord_to_selection_uses_selected_chord_when_no_range() -> None:
    window = _Window()

    gui_editor_state.assign_selected_chord_to_selection(window)

    assert window.manual_chords == [ChordRegion(1.0, 2.0, "C", 0.72)]
    assert window.removed_chord_ranges == [(1.0, 2.0)]
    assert window.refreshed_with == ChordRegion(1.0, 2.0, "C", 0.72)
    assert window.status.messages == ["Assigned C to selected chord."]


def test_has_loaded_editor_project_requires_result_and_editor_project() -> None:
    window = _Window()

    assert gui_editor_state._has_loaded_editor_project(window)

    window.current_result = None

    assert not gui_editor_state._has_loaded_editor_project(window)

    window.current_result = object()
    window.editor_project = None

    assert not gui_editor_state._has_loaded_editor_project(window)


def test_delete_selected_chord_uses_visible_selected_chord_target() -> None:
    window = _Window()
    chord = window.timeline.selected_chord
    assert chord is not None
    window.manual_chords = [chord]

    gui_editor_state.delete_selected_chord(window)

    assert window.manual_chords == []
    assert window.removed_chord_ranges == [(1.0, 2.0)]
    assert window.refreshed_with is None
    assert window.status.messages == ["Deleted G."]


def test_revert_all_chord_edits_clears_overrides_and_refreshes() -> None:
    window = _Window()
    window.manual_chords = [ChordRegion(1.0, 2.0, "C", 0.9)]
    window.removed_chord_ranges = [(3.0, 4.0)]

    gui_editor_state.revert_all_chord_edits(window)

    assert window.manual_chords == []
    assert window.removed_chord_ranges == []
    assert window.refreshed_with is None
    assert window.status.messages == ["Restored all detected chords."]


def test_revert_all_chord_edits_reports_when_there_is_nothing_to_revert() -> None:
    window = _Window()

    gui_editor_state.revert_all_chord_edits(window)

    assert window.refreshed_with is None
    assert window.status.messages == ["There are no manual chord edits to revert."]


def test_generate_detected_chords_populates_blank_base_project(monkeypatch) -> None:
    chord = ChordRegion(0.0, 1.0, "C", 0.8)
    project = EditorProject(
        project_dir=Path("project"),
        source_audio=Path("song.wav"),
        tracks=[],
        notes=[],
        chords=[],
        duration=1.0,
    )
    saved: list[tuple[object, bool]] = []
    monkeypatch.setattr(gui_editor_state, "detect_chords", lambda _notes: [chord])
    monkeypatch.setattr(
        gui_editor_state,
        "update_project_editor_state",
        lambda project_dir, *, generate_chord_suggestions: saved.append(
            (project_dir, generate_chord_suggestions)
        ),
    )
    button = SimpleNamespace(enabled=False, setEnabled=lambda enabled: setattr(button, "enabled", enabled))
    window = SimpleNamespace(
        current_result=SimpleNamespace(project_dir=Path("project")),
        base_editor_project=project,
        editor_project=project,
        previous_chord_button=button,
        next_chord_button=SimpleNamespace(setEnabled=lambda _enabled: None),
        logger=SimpleNamespace(exception=lambda *_args: None),
        generate_chord_suggestions=SimpleNamespace(
            blockSignals=lambda _blocked: False,
            setChecked=lambda checked: setattr(window, "suggestions_checked", checked),
        ),
        status=_StatusBar(),
        suggestions_checked=False,
        messages=queue.Queue(),
        detect_chords_button=SimpleNamespace(setEnabled=lambda _enabled: None),
        begin_activity=lambda _message: None,
        end_activity=lambda _message="Ready": None,
    )
    window.statusBar = lambda: window.status

    def refresh(_selected) -> None:
        window.editor_project = window.base_editor_project

    window.refresh_editor_project_from_chord_edits = refresh

    gui_editor_state.generate_detected_chords(window)
    window.chord_detection_worker.join(timeout=5)
    kind, base_project, chords, error = window.messages.get_nowait()
    assert (kind, base_project, error) == ("CHORDS_DETECTED", project, None)
    gui_editor_state.finish_detected_chords(window, base_project, chords, error)

    assert window.base_editor_project.chords == [chord]
    assert saved == [(Path("project"), True)]
    assert window.suggestions_checked is True
    assert button.enabled is True
    assert window.status.messages == ["Generated 1 chord suggestions."]


def test_finish_detected_chords_ignores_result_for_replaced_project() -> None:
    project = EditorProject(
        project_dir=Path("project"),
        source_audio=Path("song.wav"),
        tracks=[],
        notes=[],
        chords=[],
        duration=1.0,
    )
    ended: list[str] = []
    window = SimpleNamespace(
        current_result=SimpleNamespace(project_dir=Path("project")),
        base_editor_project=None,
        logger=SimpleNamespace(info=lambda *_args: None),
        end_activity=lambda message="Ready": ended.append(message),
    )

    gui_editor_state.finish_detected_chords(window, project, [ChordRegion(0.0, 1.0, "C", 0.8)], None)

    assert window.base_editor_project is None
    assert ended == ["Ready"]
