from __future__ import annotations

from pitchstems.chord_regions import merge_chord_ranges
from pitchstems.editor_project import ChordRegion


def review_ranges(
    selection_ranges: list[tuple[float, float]],
    selected_chord: ChordRegion | None,
) -> list[tuple[float, float]]:
    explicit_ranges = merge_chord_ranges(selection_ranges)
    if explicit_ranges:
        return explicit_ranges
    if selected_chord is None:
        return []
    return [(selected_chord.start, selected_chord.end)]


def single_review_range(ranges: list[tuple[float, float]]) -> tuple[float, float] | None:
    if len(ranges) != 1:
        return None
    return ranges[0]
