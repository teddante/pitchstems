from __future__ import annotations


def merge_chord_ranges(ranges: list[tuple[float, float]]) -> list[tuple[float, float]]:
    valid = sorted((start, end) for start, end in ranges if end > start)
    merged: list[tuple[float, float]] = []
    for start, end in valid:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged
