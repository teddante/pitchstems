import pytest


pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402

from pitchstems.editor_project import ChordRegion  # noqa: E402
from pitchstems import gui_editor_state  # noqa: E402


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

    def showMessage(self, message: str, _timeout: int) -> None:  # noqa: N802 - Qt API shape
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

    def statusBar(self) -> _StatusBar:  # noqa: N802 - Qt API shape
        return self.status


def test_assign_selected_chord_to_selection_uses_selected_chord_when_no_range() -> None:
    window = _Window()

    gui_editor_state.assign_selected_chord_to_selection(window)

    assert window.manual_chords == [ChordRegion(1.0, 2.0, "C", 0.72)]
    assert window.removed_chord_ranges == [(1.0, 2.0)]
    assert window.refreshed_with == ChordRegion(1.0, 2.0, "C", 0.72)
    assert window.status.messages == ["Assigned C to selected chord."]
