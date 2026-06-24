from __future__ import annotations

from pitchstems.chord_regions import merge_or_selected_chord_range
from pitchstems.editor_project import ChordRegion
from pitchstems.time_format import format_time


def chord_assignment_ranges(
    selection_ranges: list[tuple[float, float]],
    selected_chord: ChordRegion | None,
) -> list[tuple[float, float]]:
    return merge_or_selected_chord_range(selection_ranges, selected_chord)


def chord_assignment_target_text(
    ranges: list[tuple[float, float]],
    selected_chord: ChordRegion | None,
) -> str:
    if not ranges:
        return "no selection"
    if selected_chord is not None and ranges == [(selected_chord.start, selected_chord.end)]:
        return "selected chord"
    if len(ranges) == 1:
        return f"{format_time(ranges[0][0])} - {format_time(ranges[0][1])}"
    return f"{len(ranges)} ranges"
