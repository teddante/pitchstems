from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Callable, Literal, Protocol

from pitchstems.editor_models import ChordRegion


class TimelineTrack(Protocol):
    name: str


ChordDragMode = Literal["move", "resize_start", "resize_end"]


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


def chord_drag_mode(
    *,
    seconds: float,
    chord: ChordRegion,
    pixels_per_second: float,
) -> ChordDragMode:
    edge = max(0.04, 8 / pixels_per_second)
    if abs(seconds - chord.start) <= edge:
        return "resize_start"
    if abs(seconds - chord.end) <= edge:
        return "resize_end"
    return "move"


def neighbour_chords(
    chords: Sequence[ChordRegion],
    chord: ChordRegion,
) -> tuple[ChordRegion | None, ChordRegion | None]:
    other_chords = [other for other in chords if other != chord]
    previous = max(
        (other for other in other_chords if other.end <= chord.start),
        key=lambda item: item.end,
        default=None,
    )
    next_chord = min(
        (other for other in other_chords if other.start >= chord.end),
        key=lambda item: item.start,
        default=None,
    )
    return previous, next_chord


def dragged_chord_region(
    *,
    original: ChordRegion,
    mode: ChordDragMode,
    press_seconds: float,
    seconds: float,
    duration: float,
    previous_chord: ChordRegion | None,
    next_chord: ChordRegion | None,
    minimum_length: float,
    snap_seconds: Callable[[float], tuple[float, float]],
    snap_enabled: bool = True,
) -> ChordRegion:
    lower_bound = previous_chord.end if previous_chord else 0.0
    upper_bound = next_chord.start if next_chord else duration
    if mode == "move":
        delta = seconds - press_seconds
        length = min(original.duration, max(minimum_length, upper_bound - lower_bound))
        start = max(lower_bound, min(original.start + delta, max(lower_bound, upper_bound - length)))
        end = start + length
        if snap_enabled:
            snapped_start, start_delta = snap_seconds(start)
            snapped_end, end_delta = snap_seconds(end)
            if abs(start_delta) <= abs(end_delta):
                start = max(lower_bound, min(snapped_start, upper_bound - length))
                end = start + length
            else:
                end = min(upper_bound, max(snapped_end, lower_bound + length))
                start = end - length
    elif mode == "resize_start":
        end = original.end
        start = max(lower_bound, min(seconds, end - minimum_length))
        if snap_enabled:
            start = max(lower_bound, min(snap_seconds(start)[0], end - minimum_length))
    else:
        start = original.start
        end = min(upper_bound, max(seconds, start + minimum_length))
        if snap_enabled:
            end = min(upper_bound, max(snap_seconds(end)[0], start + minimum_length))
    return ChordRegion(start=start, end=end, label=original.label, confidence=original.confidence)


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
