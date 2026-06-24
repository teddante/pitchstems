from __future__ import annotations

from pitchstems.chord_regions import merge_chord_ranges


MIN_SELECTION_SECONDS = 0.05


def clamp_selection_bounds(start: float, end: float, duration: float) -> tuple[float, float]:
    duration = max(duration, 0.0)
    return max(0.0, min(start, duration)), max(0.0, min(end, duration))


def active_selection_range(
    start: float | None,
    end: float | None,
    min_duration: float = MIN_SELECTION_SECONDS,
) -> tuple[float, float] | None:
    if start is None or end is None:
        return None
    lower, upper = sorted((start, end))
    if upper - lower < min_duration:
        return None
    return lower, upper


def merged_selection_ranges(
    committed_ranges: list[tuple[float, float]],
    current_range: tuple[float, float] | None,
) -> list[tuple[float, float]]:
    ranges = list(committed_ranges)
    if current_range is not None:
        ranges.append(current_range)
    return merge_chord_ranges(ranges)


def commit_selection_range(
    committed_ranges: list[tuple[float, float]],
    current_range: tuple[float, float] | None,
    additive: bool,
) -> list[tuple[float, float]]:
    if current_range is None:
        return list(committed_ranges) if additive else []
    if additive:
        return merge_chord_ranges([*committed_ranges, current_range])
    return [current_range]
