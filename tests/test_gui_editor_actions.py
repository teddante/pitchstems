from __future__ import annotations

from dataclasses import dataclass, field

from pitchstems.editor_project import ChordRegion
from pitchstems.gui_editor_actions import (
    fit_editor_review_to_view,
    fit_editor_song_to_view,
    select_review_chord,
)


@dataclass
class FakeStatusBar:
    messages: list[tuple[str, int]] = field(default_factory=list)

    def showMessage(self, message: str, timeout: int = 0) -> None:
        self.messages.append((message, timeout))


@dataclass
class FakeTimeline:
    ranges: list[tuple[float, float]] = field(default_factory=list)
    selected_chord: ChordRegion | None = None
    fit_range_result: bool = True
    next_chord: ChordRegion | None = None
    fitted_song: bool = False
    fitted_ranges: list[tuple[float, float]] = field(default_factory=list)
    chord_directions: list[int] = field(default_factory=list)

    def selection_ranges(self) -> list[tuple[float, float]]:
        return self.ranges

    def fit_song_to_view(self) -> None:
        self.fitted_song = True

    def fit_time_range_to_view(self, start: float, end: float) -> bool:
        self.fitted_ranges.append((start, end))
        return self.fit_range_result

    def select_review_chord(self, direction: int) -> ChordRegion | None:
        self.chord_directions.append(direction)
        return self.next_chord


@dataclass
class FakeWindow:
    editor_project: object | None = object()
    timeline: FakeTimeline = field(default_factory=FakeTimeline)
    status_bar: FakeStatusBar = field(default_factory=FakeStatusBar)
    chord_actions_refreshed: int = 0

    def statusBar(self) -> FakeStatusBar:
        return self.status_bar

    def refresh_chord_actions(self) -> None:
        self.chord_actions_refreshed += 1


def test_fit_song_requires_project() -> None:
    window = FakeWindow(editor_project=None)

    fit_editor_song_to_view(window)

    assert not window.timeline.fitted_song
    assert window.status_bar.messages == [("Open or run a project before fitting the song view.", 4000)]


def test_fit_song_runs_on_loaded_project() -> None:
    window = FakeWindow()

    fit_editor_song_to_view(window)

    assert window.timeline.fitted_song
    assert window.status_bar.messages == [("Showing the whole song horizontally and vertically.", 4000)]


def test_fit_review_target_prefers_explicit_ranges() -> None:
    window = FakeWindow(
        timeline=FakeTimeline(
            ranges=[(3.0, 4.0), (1.0, 2.0)],
            selected_chord=ChordRegion(8.0, 9.0, "D", 0.8),
        )
    )

    fit_editor_review_to_view(window)

    assert window.timeline.fitted_ranges == [(1.0, 4.0)]
    assert window.status_bar.messages == [("Timeline fit to review target.", 3000)]


def test_fit_review_target_uses_selected_chord() -> None:
    window = FakeWindow(timeline=FakeTimeline(selected_chord=ChordRegion(2.5, 3.25, "C", 0.8)))

    fit_editor_review_to_view(window)

    assert window.timeline.fitted_ranges == [(2.5, 3.25)]


def test_fit_review_target_reports_empty_and_tiny_targets() -> None:
    empty = FakeWindow()

    fit_editor_review_to_view(empty)

    assert empty.timeline.fitted_ranges == []
    assert empty.status_bar.messages == [
        ("Select a timeline range or chord before fitting the review target.", 4000)
    ]

    tiny = FakeWindow(
        timeline=FakeTimeline(ranges=[(1.0, 1.01)], fit_range_result=False),
    )

    fit_editor_review_to_view(tiny)

    assert tiny.timeline.fitted_ranges == [(1.0, 1.01)]
    assert tiny.status_bar.messages == [("Review target is too short to fit.", 4000)]


def test_select_review_chord_refreshes_actions_only_after_selection() -> None:
    no_chords = FakeWindow()

    select_review_chord(no_chords, 1)

    assert no_chords.timeline.chord_directions == [1]
    assert no_chords.chord_actions_refreshed == 0
    assert no_chords.status_bar.messages == [("No timeline chord available.", 3000)]

    chord = ChordRegion(1.0, 2.0, "G", 0.8)
    with_chord = FakeWindow(timeline=FakeTimeline(next_chord=chord))

    select_review_chord(with_chord, -1)

    assert with_chord.timeline.chord_directions == [-1]
    assert with_chord.chord_actions_refreshed == 1
    assert with_chord.status_bar.messages == []
