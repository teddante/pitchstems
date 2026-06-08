from __future__ import annotations

import re

from pitchstems.editor_models import ChordRegion


def compact_chord_label(label: str) -> str:
    match = re.match(r"\s*([A-G](?:#|b)?)", label)
    return match.group(1) if match else label.strip()[:2]


def snap_seconds_to_timeline_targets(
    *,
    seconds: float,
    duration: float,
    position: float,
    selection_start: float | None,
    selection_end: float | None,
    chords: list[ChordRegion],
    ignored_chord: ChordRegion,
    pixels_per_second: float,
) -> tuple[float, float]:
    threshold = max(0.035, 10 / pixels_per_second)
    targets = [0.0, duration, position]
    if selection_start is not None:
        targets.append(selection_start)
    if selection_end is not None:
        targets.append(selection_end)
    for chord in chords:
        if chord == ignored_chord:
            continue
        targets.extend([chord.start, chord.end])
    nearest = min(targets, key=lambda target: abs(target - seconds), default=seconds)
    delta = nearest - seconds
    if abs(delta) <= threshold:
        return nearest, delta
    return seconds, 0.0
