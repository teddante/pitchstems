from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Protocol

from pitchstems.editor_models import ChordRegion


class TimelineTrack(Protocol):
    name: str


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


def build_track_geometries(
    *,
    tracks: Sequence[TimelineTrack],
    visible_tracks: set[str],
    pitch_ranges: dict[str, tuple[int, int]],
    chord_height: float,
    minimum_track_height: float,
    vertical_zoom: float,
) -> dict[str, tuple[float, float, int, int]]:
    geometries: dict[str, tuple[float, float, int, int]] = {}
    y = chord_height
    for track in tracks:
        track_key = track.name.lower()
        if track_key not in visible_tracks:
            continue
        pitch_range = pitch_ranges.get(track_key)
        if pitch_range:
            low_pitch, high_pitch = pitch_range
            base_height = max(132, (high_pitch - low_pitch + 1) * 8 + 34)
            height = max(minimum_track_height, base_height * vertical_zoom)
        else:
            low_pitch = 48
            high_pitch = 72
            height = max(minimum_track_height, 132 * vertical_zoom)
        geometries[track_key] = (y, height, low_pitch, high_pitch)
        y += height
    return geometries
