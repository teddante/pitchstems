from __future__ import annotations

from typing import Protocol


class ChordRangeLike(Protocol):
    @property
    def start(self) -> float: ...

    @property
    def end(self) -> float: ...


def merge_chord_ranges(ranges: list[tuple[float, float]]) -> list[tuple[float, float]]:
    valid = sorted((start, end) for start, end in ranges if end > start)
    merged: list[tuple[float, float]] = []
    for start, end in valid:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def merge_or_selected_chord_range(
    selection_ranges: list[tuple[float, float]],
    selected_chord: ChordRangeLike | None,
) -> list[tuple[float, float]]:
    explicit_ranges = merge_chord_ranges(selection_ranges)
    if explicit_ranges:
        return explicit_ranges
    if selected_chord is None:
        return []
    return [(selected_chord.start, selected_chord.end)]
