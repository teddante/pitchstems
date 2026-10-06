"""Timeline selection ranges, review targets, and chord-review navigation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pitchstems.editor_models import ChordRegion
from pitchstems.time_format import format_time

TimeRange = tuple[float, float]
ReviewTargetMode = Literal["playhead", "selected_chord", "selection", "multi_selection"]

# Shortest range treated as a real selection, gap, or playable/fit-able review target.
MIN_RANGE_SECONDS = 0.05


# Range arithmetic


def merge_ranges(ranges: list[TimeRange]) -> list[TimeRange]:
    valid = sorted((start, end) for start, end in ranges if end > start)
    merged: list[TimeRange] = []
    for start, end in valid:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def review_ranges(
    selection_ranges: list[TimeRange],
    selected_chord: ChordRegion | None,
) -> list[TimeRange]:
    """Explicit selection ranges, or the selected chord's span when nothing is selected."""
    explicit_ranges = merge_ranges(selection_ranges)
    if explicit_ranges:
        return explicit_ranges
    if selected_chord is None:
        return []
    return [(selected_chord.start, selected_chord.end)]


def single_review_range(ranges: list[TimeRange]) -> TimeRange | None:
    if len(ranges) != 1:
        return None
    return ranges[0]


def review_playback_loop_range(
    selection_ranges: list[TimeRange],
    selected_chord: ChordRegion | None,
) -> TimeRange | None:
    return single_review_range(review_ranges(selection_ranges, selected_chord))


# Timeline drag selection


def clamp_selection_bounds(start: float, end: float, duration: float) -> TimeRange:
    duration = max(duration, 0.0)
    return max(0.0, min(start, duration)), max(0.0, min(end, duration))


def active_selection_range(
    start: float | None,
    end: float | None,
    min_duration: float = MIN_RANGE_SECONDS,
) -> TimeRange | None:
    if start is None or end is None:
        return None
    lower, upper = sorted((start, end))
    if upper - lower < min_duration:
        return None
    return lower, upper


def merged_selection_ranges(
    committed_ranges: list[TimeRange],
    current_range: TimeRange | None,
) -> list[TimeRange]:
    ranges = list(committed_ranges)
    if current_range is not None:
        ranges.append(current_range)
    return merge_ranges(ranges)


def commit_selection_range(
    committed_ranges: list[TimeRange],
    current_range: TimeRange | None,
    additive: bool,
) -> list[TimeRange]:
    if current_range is None:
        return list(committed_ranges) if additive else []
    if additive:
        return merge_ranges([*committed_ranges, current_range])
    return [current_range]


# Review targets


@dataclass(frozen=True)
class ReviewTarget:
    mode: ReviewTargetMode
    ranges: tuple[TimeRange, ...]
    chord: ChordRegion | None = None
    position_seconds: float | None = None

    @property
    def single_range(self) -> TimeRange | None:
        return single_review_range(list(self.ranges))

    @property
    def heading(self) -> str:
        return {
            "playhead": "Playhead",
            "selected_chord": "Selected chord",
            "selection": "Timeline range",
            "multi_selection": "Timeline ranges",
        }[self.mode]


def review_target(
    selection_ranges: list[TimeRange],
    selected_chord: ChordRegion | None,
    position_seconds: float,
) -> ReviewTarget:
    ranges = review_ranges(selection_ranges, selected_chord)
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


def review_navigation_chord(
    chords: list[ChordRegion],
    selected_chord: ChordRegion | None,
    position_seconds: float,
    direction: int,
) -> ChordRegion | None:
    if not chords or direction == 0:
        return None
    if selected_chord in chords:
        index = chords.index(selected_chord)
        next_index = max(0, min(len(chords) - 1, index + (1 if direction > 0 else -1)))
        return chords[next_index]
    if direction > 0:
        for chord in chords:
            if chord.end > position_seconds:
                return chord
        return chords[-1]
    for chord in reversed(chords):
        if chord.start <= position_seconds:
            return chord
    return chords[0]


# Display text


def review_range_text(review_range: TimeRange) -> str:
    start, end = review_range
    return f"{format_time(start)} - {format_time(end)}"


def review_ranges_total_seconds(ranges: list[TimeRange]) -> float:
    return sum(end - start for start, end in ranges)


def review_ranges_brief_text(ranges: list[TimeRange]) -> str:
    if len(ranges) == 1:
        return review_range_text(ranges[0])
    return f"{len(ranges)} ranges, {review_ranges_total_seconds(ranges):.2f}s total"


def review_ranges_detail_text(ranges: list[TimeRange]) -> str:
    shown_ranges = ", ".join(review_range_text(review_range) for review_range in ranges)
    return f"{len(ranges)} ranges ({review_ranges_total_seconds(ranges):.3f} sec total): {shown_ranges}"


def chord_assignment_target_text(
    ranges: list[TimeRange],
    selected_chord: ChordRegion | None,
) -> str:
    if not ranges:
        return "no selection"
    if selected_chord is not None and ranges == [(selected_chord.start, selected_chord.end)]:
        return "selected chord"
    if len(ranges) == 1:
        return review_range_text(ranges[0])
    return f"{len(ranges)} ranges"
