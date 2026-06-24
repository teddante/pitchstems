from __future__ import annotations

from pitchstems.editor_project import ChordRegion
from pitchstems.gui_harmony_flow import HarmonyRefreshGate, chord_context_key


def test_harmony_refresh_gate_allows_initial_and_throttles_close_updates() -> None:
    gate = HarmonyRefreshGate(min_interval_seconds=0.25)
    assert gate.should_refresh(10.0, now_seconds=1.00)
    assert not gate.should_refresh(10.1, now_seconds=1.10)
    assert gate.should_refresh(10.2, now_seconds=1.26)


def test_harmony_refresh_gate_forces_selection_changes() -> None:
    gate = HarmonyRefreshGate(min_interval_seconds=0.25)
    assert gate.should_refresh(10.0, now_seconds=1.00)
    assert gate.should_refresh(10.0, now_seconds=1.05, force=True)


def test_chord_context_key_uses_selected_chord_when_no_explicit_selection() -> None:
    window = _Window([], ChordRegion(1.0, 2.0, "G", 0.8))

    assert chord_context_key(window, 9.0) == ("selection", 1.0, 2.0)


def test_chord_context_key_prefers_explicit_selection_over_selected_chord() -> None:
    window = _Window([(3.0, 4.0)], ChordRegion(1.0, 2.0, "G", 0.8))

    assert chord_context_key(window, 9.0) == ("selection", 3.0, 4.0)


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
        ranges: list[tuple[float, float]],
        selected_chord: ChordRegion | None,
    ) -> None:
        self.timeline = _Timeline(ranges, selected_chord)
