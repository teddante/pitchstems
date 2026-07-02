from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pitchstems.chord_regions import merge_or_selected_chord_range
from pitchstems.editor_project import ChordRegion
from pitchstems.time_format import format_time

ReviewTargetMode = Literal["playhead", "selected_chord", "selection", "multi_selection"]


@dataclass(frozen=True)
class ReviewTarget:
    mode: ReviewTargetMode
    ranges: tuple[tuple[float, float], ...]
    chord: ChordRegion | None = None
    position_seconds: float | None = None

    @property
    def single_range(self) -> tuple[float, float] | None:
        return single_review_range(list(self.ranges))

    @property
    def is_range_based(self) -> bool:
        return bool(self.ranges)

    @property
    def heading(self) -> str:
        return {
            "playhead": "Playhead",
            "selected_chord": "Selected chord",
            "selection": "Timeline range",
            "multi_selection": "Timeline ranges",
        }[self.mode]


def review_ranges(
    selection_ranges: list[tuple[float, float]],
    selected_chord: ChordRegion | None,
) -> list[tuple[float, float]]:
    return merge_or_selected_chord_range(selection_ranges, selected_chord)


def review_target(
    selection_ranges: list[tuple[float, float]],
    selected_chord: ChordRegion | None,
    position_seconds: float,
) -> ReviewTarget:
    ranges = merge_or_selected_chord_range(selection_ranges, selected_chord)
    if selection_ranges:
        mode: ReviewTargetMode = "multi_selection" if len(ranges) > 1 else "selection"
        return ReviewTarget(mode=mode, ranges=tuple(ranges), position_seconds=position_seconds)
    if selected_chord is not None:
        return ReviewTarget(
            mode="selected_chord",
            ranges=((selected_chord.start, selected_chord.end),),
            chord=selected_chord,
            position_seconds=position_seconds,
        )
    return ReviewTarget(mode="playhead", ranges=(), position_seconds=position_seconds)


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
