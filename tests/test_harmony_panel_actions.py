import pytest


pytest.importorskip("PySide6")

from PySide6.QtCore import Qt

from pitchstems.editor_project import ChordRegion
from pitchstems.harmony_panel import refresh_chord_actions


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
    def data(self, role: int):
        if role == Qt.UserRole:
            return "C"
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
