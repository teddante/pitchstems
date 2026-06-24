from __future__ import annotations

from typing import Protocol

from pitchstems.editor_project import ChordRegion
from pitchstems.editor_review_target import review_ranges


class _StatusBar(Protocol):
    def showMessage(self, message: str, timeout: int = 0) -> None: ...


class _Timeline(Protocol):
    selected_chord: ChordRegion | None

    def selection_ranges(self) -> list[tuple[float, float]]: ...

    def fit_song_to_view(self) -> None: ...

    def fit_time_range_to_view(self, start: float, end: float) -> bool: ...

    def select_review_chord(self, direction: int) -> ChordRegion | None: ...


class _EditorWindow(Protocol):
    editor_project: object | None
    timeline: _Timeline

    def statusBar(self) -> _StatusBar: ...

    def refresh_chord_actions(self) -> None: ...


def fit_editor_song_to_view(window: _EditorWindow) -> None:
    if window.editor_project is None:
        window.statusBar().showMessage("Open or run a project before fitting the song view.", 4000)
        return
    window.timeline.fit_song_to_view()
    window.statusBar().showMessage("Showing the whole song horizontally and vertically.", 4000)


def fit_editor_review_to_view(window: _EditorWindow) -> None:
    if window.editor_project is None:
        window.statusBar().showMessage("Open or run a project before fitting the review target.", 4000)
        return
    ranges = review_ranges(window.timeline.selection_ranges(), window.timeline.selected_chord)
    if not ranges:
        window.statusBar().showMessage("Select a timeline range or chord before fitting the review target.", 4000)
        return
    start = min(start for start, _end in ranges)
    end = max(end for _start, end in ranges)
    if not window.timeline.fit_time_range_to_view(start, end):
        window.statusBar().showMessage("Review target is too short to fit.", 4000)
        return
    window.statusBar().showMessage("Timeline fit to review target.", 3000)


def select_review_chord(window: _EditorWindow, direction: int) -> None:
    chord = window.timeline.select_review_chord(direction)
    if chord is None:
        window.statusBar().showMessage("No timeline chord available.", 3000)
        return
    window.refresh_chord_actions()
