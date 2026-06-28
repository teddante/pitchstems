from __future__ import annotations

from pitchstems.chord_regions import merge_or_selected_chord_range
from pitchstems.editor_project import ChordRegion
from pitchstems.time_format import format_time


def review_ranges(
    selection_ranges: list[tuple[float, float]],
    selected_chord: ChordRegion | None,
) -> list[tuple[float, float]]:
    return merge_or_selected_chord_range(selection_ranges, selected_chord)


def single_review_range(ranges: list[tuple[float, float]]) -> tuple[float, float] | None:
    if len(ranges) != 1:
        return None
    return ranges[0]


def review_range_text(review_range: tuple[float, float]) -> str:
    start, end = review_range
    return f"{format_time(start)} - {format_time(end)}"


def review_ranges_total_seconds(ranges: list[tuple[float, float]]) -> float:
    return sum(end - start for start, end in ranges)


def review_ranges_brief_text(ranges: list[tuple[float, float]]) -> str:
    if len(ranges) == 1:
        return review_range_text(ranges[0])
    return f"{len(ranges)} ranges, {review_ranges_total_seconds(ranges):.2f}s total"


def review_ranges_detail_text(ranges: list[tuple[float, float]]) -> str:
    shown_ranges = ", ".join(review_range_text(review_range) for review_range in ranges)
    return f"{len(ranges)} ranges ({review_ranges_total_seconds(ranges):.3f} sec total): {shown_ranges}"
