from __future__ import annotations

from pitchstems.editor_project import ChordRegion
from pitchstems.editor_review_target import review_ranges, single_review_range


def playback_loop_range(
    selection: tuple[float, float] | None,
    selected_chord: ChordRegion | None,
) -> tuple[float, float] | None:
    if selection is not None:
        return selection
    if selected_chord is None:
        return None
    return selected_chord.start, selected_chord.end


def review_playback_loop_range(
    selection_ranges: list[tuple[float, float]],
    selected_chord: ChordRegion | None,
) -> tuple[float, float] | None:
    return single_review_range(review_ranges(selection_ranges, selected_chord))
