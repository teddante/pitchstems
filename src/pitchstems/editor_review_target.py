from __future__ import annotations

from pitchstems.chord_regions import merge_or_selected_chord_range
from pitchstems.editor_project import ChordRegion


def review_ranges(
    selection_ranges: list[tuple[float, float]],
    selected_chord: ChordRegion | None,
) -> list[tuple[float, float]]:
    return merge_or_selected_chord_range(selection_ranges, selected_chord)


def single_review_range(ranges: list[tuple[float, float]]) -> tuple[float, float] | None:
    if len(ranges) != 1:
        return None
    return ranges[0]
