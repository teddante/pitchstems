from __future__ import annotations

import random

from pitchstems.editor_models import NoteEvent
from pitchstems.notation import pitch_class_for_name

SCALE_PREVIEW_PATTERNS = {
    "up_down": "Up + down",
    "up": "Up only",
    "down": "Down only",
    "random": "Random",
}


def scale_preview_notes(
    label: str,
    note_names: list[str],
    pattern: str = "up_down",
    *,
    low_pitch: int | None = None,
    high_pitch: int | None = None,
) -> list[NoteEvent]:
    pitches = scale_preview_pitches(label, note_names, pattern, low_pitch=low_pitch, high_pitch=high_pitch)
    note_duration = 0.16 if pattern != "random" else 0.11
    gap = 0.015
    return [
        NoteEvent(
            stem="scale-preview",
            start=index * (note_duration + gap),
            end=index * (note_duration + gap) + note_duration,
            pitch=pitch,
            velocity=86,
        )
        for index, pitch in enumerate(pitches)
    ]


def scale_preview_pitches(
    label: str,
    note_names: list[str],
    pattern: str = "up_down",
    *,
    low_pitch: int | None = None,
    high_pitch: int | None = None,
) -> list[int]:
    ascending = (
        _ranged_scale_pitches(note_names, low_pitch, high_pitch)
        if low_pitch is not None and high_pitch is not None
        else _ascending_scale_pitches(note_names)
    )
    if not ascending:
        return []
    if pattern == "up":
        return ascending
    if pattern == "down":
        return list(reversed(ascending))
    if pattern == "random":
        return _random_scale_pitches(label, ascending)
    return [*ascending, *reversed(ascending[:-1])]


def _ascending_scale_pitches(note_names: list[str]) -> list[int]:
    pitch_classes = [_pitch_class(note_name) for note_name in note_names]
    if not pitch_classes:
        return []
    pitches: list[int] = []
    previous: int | None = None
    for pitch_class in pitch_classes:
        pitch = 60 + pitch_class
        while previous is not None and pitch <= previous:
            pitch += 12
        pitches.append(pitch)
        previous = pitch
    pitches.append(pitches[0] + 12)
    return pitches


def _random_scale_pitches(label: str, ascending: list[int]) -> list[int]:
    pool = ascending[:-1] or ascending
    generator = random.Random(f"{label}|{','.join(str(pitch) for pitch in ascending)}")
    return [generator.choice(pool) for _index in range(min(12, max(6, len(pool) * 2)))]


def _pitch_class(note_name: str) -> int:
    return pitch_class_for_name(note_name) or 0


def _ranged_scale_pitches(note_names: list[str], low_pitch: int, high_pitch: int) -> list[int]:
    low, high = _normalized_range(low_pitch, high_pitch)
    pitch_classes = {_pitch_class(note_name) for note_name in note_names}
    return [
        pitch
        for pitch in range(low, high + 1)
        if pitch % 12 in pitch_classes
    ]


def _normalized_range(low_pitch: int, high_pitch: int) -> tuple[int, int]:
    low = int(low_pitch)
    high = int(high_pitch)
    return (low, high) if low <= high else (high, low)
