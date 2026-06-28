from __future__ import annotations

import pitchstems.gui_harmony_flow as gui_harmony_flow
from pitchstems.editor_project import ChordRegion
from pitchstems.gui_harmony_flow import (
    HarmonyRefreshGate,
    chord_context_key,
    current_chord_gap_range,
    refresh_current_gap_suggestions,
    refresh_current_theory,
)


def test_harmony_refresh_gate_allows_initial_and_throttles_close_updates() -> None:
    gate = HarmonyRefreshGate(min_interval_seconds=0.25)
    assert gate.should_refresh(now_seconds=1.00)
    assert not gate.should_refresh(now_seconds=1.10)
    assert gate.should_refresh(now_seconds=1.26)


def test_harmony_refresh_gate_forces_selection_changes() -> None:
    gate = HarmonyRefreshGate(min_interval_seconds=0.25)
    assert gate.should_refresh(now_seconds=1.00)
    assert gate.should_refresh(now_seconds=1.05, force=True)


def test_chord_context_key_uses_selected_chord_when_no_explicit_selection() -> None:
    window = _Window([], ChordRegion(1.0, 2.0, "G", 0.8))

    assert chord_context_key(window, 9.0) == ("selection", 1.0, 2.0)


def test_chord_context_key_prefers_explicit_selection_over_selected_chord() -> None:
    window = _Window([(3.0, 4.0)], ChordRegion(1.0, 2.0, "G", 0.8))

    assert chord_context_key(window, 9.0) == ("selection", 3.0, 4.0)


def test_current_chord_gap_range_uses_selection_when_present() -> None:
    window = _GapWindow(selection=(2.0, 3.0), gap=(4.0, 5.0))

    assert current_chord_gap_range(window) == (2.0, 3.0)


def test_current_chord_gap_range_rejects_tiny_selection() -> None:
    window = _GapWindow(selection=(2.0, 2.01), gap=(4.0, 5.0))

    assert current_chord_gap_range(window) is None


def test_current_chord_gap_range_falls_back_to_playhead_gap() -> None:
    window = _GapWindow(selection=None, gap=(4.0, 5.0), position=4.25)

    assert current_chord_gap_range(window) == (4.0, 5.0)
    assert window.editor_project.chord_index.positions == [4.25]


def test_current_chord_gap_range_requires_project() -> None:
    window = _GapWindow(selection=(2.0, 3.0), gap=(4.0, 5.0))
    window.editor_project = None

    assert current_chord_gap_range(window) is None


def test_refresh_current_gap_suggestions_sets_analysis(monkeypatch) -> None:
    window = _GapWindow(selection=(2.0, 3.0), gap=None)
    source_notes = [object()]
    calls = []

    def fake_analyze_chord_gap(notes, chords, start, end, *, scoring_options):
        calls.append((notes, chords, start, end, scoring_options))
        return "analysis"

    monkeypatch.setattr(gui_harmony_flow, "analyze_chord_gap", fake_analyze_chord_gap)

    refresh_current_gap_suggestions(window, source_notes)

    assert calls == [(source_notes, window.editor_project.chords, 2.0, 3.0, "scoring")]
    assert window.gap_analyses == ["analysis"]


def test_refresh_current_gap_suggestions_clears_when_no_gap() -> None:
    window = _GapWindow(selection=None, gap=None)

    refresh_current_gap_suggestions(window, [])

    assert window.gap_analyses == [None]


def test_refresh_current_theory_clears_without_project() -> None:
    window = _TheoryWindow(ranges=[])
    window.editor_project = None

    refresh_current_theory(window, [], 1.25)

    assert window.theory_analyses == [None]


def test_refresh_current_theory_clears_multiple_review_ranges() -> None:
    window = _TheoryWindow(ranges=[(1.0, 2.0), (3.0, 4.0)])

    refresh_current_theory(window, [], 1.25)

    assert window.theory_analyses == [None]


def test_refresh_current_theory_uses_selected_region(monkeypatch) -> None:
    window = _TheoryWindow(ranges=[(1.0, 2.0)])
    source_notes = [object()]
    calls = []

    def fake_analyze_theory_region(notes, chords, start, end):
        calls.append((notes, chords, start, end))
        return "region analysis"

    monkeypatch.setattr(gui_harmony_flow, "analyze_theory_region", fake_analyze_theory_region)

    refresh_current_theory(window, source_notes, 9.0)

    assert calls == [(source_notes, window.editor_project.chords, 1.0, 2.0)]
    assert window.theory_analyses == ["region analysis"]


def test_refresh_current_theory_uses_playhead_without_selection(monkeypatch) -> None:
    window = _TheoryWindow(ranges=[])
    source_notes = [object()]
    calls = []

    def fake_analyze_theory_at(notes, chords, seconds):
        calls.append((notes, chords, seconds))
        return "point analysis"

    monkeypatch.setattr(gui_harmony_flow, "analyze_theory_at", fake_analyze_theory_at)

    refresh_current_theory(window, source_notes, 9.0)

    assert calls == [(source_notes, window.editor_project.chords, 9.0)]
    assert window.theory_analyses == ["point analysis"]


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


class _GapIndex:
    def __init__(self, gap: tuple[float, float] | None) -> None:
        self.gap = gap
        self.positions: list[float] = []

    def gap_at(self, position: float) -> tuple[float, float] | None:
        self.positions.append(position)
        return self.gap


class _GapProject:
    def __init__(self, gap: tuple[float, float] | None) -> None:
        self.chords = [ChordRegion(0.0, 1.0, "C", 0.8)]
        self.chord_index = _GapIndex(gap)


class _GapTimeline:
    def __init__(self, selection: tuple[float, float] | None, position: float) -> None:
        self._selection = selection
        self.position = position

    def selection_range(self) -> tuple[float, float] | None:
        return self._selection


class _GapWindow:
    def __init__(
        self,
        selection: tuple[float, float] | None,
        gap: tuple[float, float] | None,
        position: float = 0.0,
    ) -> None:
        self.timeline = _GapTimeline(selection, position)
        self.editor_project: _GapProject | None = _GapProject(gap)
        self.gap_analyses = []

    def chord_scoring_options(self) -> str:
        return "scoring"

    def set_gap_analysis(self, analysis) -> None:
        self.gap_analyses.append(analysis)


class _TheoryProject:
    def __init__(self) -> None:
        self.chords = [ChordRegion(0.0, 1.0, "C", 0.8)]


class _TheoryWindow:
    def __init__(
        self,
        ranges: list[tuple[float, float]],
        selected_chord: ChordRegion | None = None,
    ) -> None:
        self.timeline = _Timeline(ranges, selected_chord)
        self.editor_project: _TheoryProject | None = _TheoryProject()
        self.theory_analyses = []

    def set_theory_analysis(self, analysis) -> None:
        self.theory_analyses.append(analysis)
