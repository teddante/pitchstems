import pytest


pytest.importorskip("PySide6")

from PySide6.QtCore import Qt

from pitchstems.editor_project import ChordRegion
from pitchstems.harmony_panel import partial_hint_text, refresh_chord_actions, refresh_chord_keyboard
from pitchstems.notation import pitch_class_name


class _Button:
    def __init__(self) -> None:
        self.enabled = False
        self.text = ""
        self.tooltip = ""

    def setEnabled(self, enabled: bool) -> None:
        self.enabled = enabled

    def setText(self, text: str) -> None:
        self.text = text

    def setToolTip(self, tooltip: str) -> None:
        self.tooltip = tooltip


class _Item:
    def __init__(self, label: str = "C", note_names: list[str] | None = None) -> None:
        self.label = label
        self.note_names = note_names or []

    def data(self, role: int):
        if role == Qt.UserRole:
            return self.label
        if role == Qt.UserRole + 2:
            return self.note_names
        return None


class _ChordList:
    def __init__(self, item=None) -> None:
        self.item = item

    def currentItem(self):
        return self.item


class _Timeline:
    def __init__(
        self,
        ranges: list[tuple[float, float]],
        selected_chord: ChordRegion | None,
    ) -> None:
        self._ranges = ranges
        self.selected_chord = selected_chord
        self.position = 0.0

    def selection_ranges(self) -> list[tuple[float, float]]:
        return self._ranges


class _Window:
    def __init__(
        self,
        item=None,
        ranges: list[tuple[float, float]] | None = None,
        selected_chord: ChordRegion | None = None,
    ) -> None:
        self.chord_list = _ChordList(item)
        self.timeline = _Timeline(ranges or [], selected_chord)
        self.preview_chord_button = _Button()
        self.use_chord_button = _Button()
        self.delete_chord_button = _Button()
        self.editor_project = None
        self.piano_chord_view = _PianoChordView()

    def display_chord(self, label: str | None) -> str:
        return {"Bb/D": "A#/D"}.get(label, label or "No clear chord")

    def display_chord_tones(self, label: str) -> list[str]:
        return ["A#", "D", "F"] if label == "Bb/D" else ["C", "E", "G"]

    def display_pitch_class_name(self, pitch_class: int) -> str:
        return pitch_class_name(pitch_class, "sharp")

    def preview_voicing_source_label(self) -> str:
        return "Preview bass D"

    def preview_voicing_note_roles(self, label: str) -> dict[int, set[str]]:
        return {2: {"bass"}} if label == "Bb/D" else {}


class _PianoChordView:
    def __init__(self) -> None:
        self.calls = []

    def set_chord(self, label, note_names, source_label="Selected chord", note_roles=None) -> None:
        self.calls.append((label, note_names, source_label, note_roles or {}))


def test_refresh_chord_actions_targets_selected_chord_without_selection() -> None:
    window = _Window(_Item(), selected_chord=ChordRegion(1.0, 2.0, "G", 0.8))

    refresh_chord_actions(window)

    assert window.preview_chord_button.enabled
    assert window.use_chord_button.enabled
    assert window.delete_chord_button.enabled
    assert window.use_chord_button.text == "Use for Chord"
    assert "selected chord" in window.use_chord_button.tooltip
    assert "Remove the selected chord" in window.delete_chord_button.tooltip


def test_refresh_chord_actions_keeps_explicit_selection_first() -> None:
    window = _Window(
        _Item(),
        ranges=[(0.0, 1.0)],
        selected_chord=ChordRegion(1.0, 2.0, "G", 0.8),
    )

    refresh_chord_actions(window)

    assert window.use_chord_button.enabled
    assert window.use_chord_button.text == "Use for Selection"
    assert not window.delete_chord_button.enabled


def test_refresh_chord_actions_disables_use_without_target() -> None:
    window = _Window(_Item())

    refresh_chord_actions(window)

    assert window.preview_chord_button.enabled
    assert not window.use_chord_button.enabled
    assert not window.delete_chord_button.enabled


def test_refresh_chord_keyboard_uses_display_spelling_for_inspector_title() -> None:
    item = _Item("Bb/D", ["A#", "D", "F"])
    window = _Window(item)

    refresh_chord_keyboard(window)

    assert window.piano_chord_view.calls == [("A#/D", ["A#", "D", "F"], "Preview bass D", {2: {"bass"}})]


class _Analysis:
    pitch_classes = [2, 3, 10]
    bass = 3


def test_partial_hint_text_formats_detected_note_set_with_window_spelling() -> None:
    assert partial_hint_text(_Window(), _Analysis(), "Detected note set: Eb - Bb - D.") == (
        "Detected note set: D# - A# - D."
    )
