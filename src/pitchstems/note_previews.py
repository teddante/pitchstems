"""Note sequences for auditioning single notes, chords, and scales."""

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


def single_note_preview_notes(pitch: int, duration: float = 0.55) -> list[NoteEvent]:
    return [
        NoteEvent(
            stem="note-preview",
            start=0.0,
            end=duration,
            pitch=max(0, min(127, pitch)),
            velocity=96,
        )
    ]


def chord_preview_pitches(
    label: str,
    note_names: list[str],
    *,
    bass_name: str | None = None,
    top_name: str | None = None,
    low_pitch: int | None = None,
    high_pitch: int | None = None,
) -> list[int]:
    bass = bass_name or _slash_bass_name(label)
    if low_pitch is not None and high_pitch is not None:
        pitch_classes = {_pitch_class(note_name) for note_name in note_names}
        if bass:
            pitch_classes.add(_pitch_class(bass))
        pitches = _pitches_in_range(pitch_classes, low_pitch, high_pitch)
        if pitches or not note_names:
            return pitches
        low, high = _normalized_range(low_pitch, high_pitch)
        return [min(max(_stacked_pitches(note_names, 48)[0], low), high)]
    pitches = (
        _top_voiced_pitches(note_names, top_name) if top_name else _stacked_pitches(note_names, 48)
    )
    if bass:
        pitches.insert(0, 36 + _pitch_class(bass))
    return pitches


def chord_preview_notes(
    label: str,
    note_names: list[str],
    *,
    bass_name: str | None = None,
    top_name: str | None = None,
    low_pitch: int | None = None,
    high_pitch: int | None = None,
) -> list[NoteEvent]:
    return [
        NoteEvent(stem="official-chord", start=0.0, end=1.45, pitch=pitch, velocity=92)
        for pitch in chord_preview_pitches(
            label,
            note_names,
            bass_name=bass_name,
            top_name=top_name,
            low_pitch=low_pitch,
            high_pitch=high_pitch,
        )
    ]


def scale_preview_pitches(
    label: str,
    note_names: list[str],
    pattern: str = "up_down",
    *,
    low_pitch: int | None = None,
    high_pitch: int | None = None,
) -> list[int]:
    if low_pitch is not None and high_pitch is not None:
        ascending = _pitches_in_range(
            {_pitch_class(note_name) for note_name in note_names},
            low_pitch,
            high_pitch,
        )
    else:
        ascending = _stacked_pitches(note_names, 60)
        if ascending:
            ascending.append(ascending[0] + 12)
    if not ascending:
        return []
    if pattern == "up":
        return ascending
    if pattern == "down":
        return list(reversed(ascending))
    if pattern == "random":
        return _random_scale_pitches(label, ascending)
    return [*ascending, *reversed(ascending[:-1])]


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


def _stacked_pitches(note_names: list[str], base_pitch: int) -> list[int]:
    """Place each note name above the previous one, starting from ``base_pitch``'s octave."""
    pitches: list[int] = []
    for note_name in note_names:
        pitch = base_pitch + _pitch_class(note_name)
        while pitches and pitch <= pitches[-1]:
            pitch += 12
        pitches.append(pitch)
    return pitches


def _pitches_in_range(pitch_classes: set[int], low_pitch: int, high_pitch: int) -> list[int]:
    low, high = _normalized_range(low_pitch, high_pitch)
    return [pitch for pitch in range(low, high + 1) if pitch % 12 in pitch_classes]


def _top_voiced_pitches(note_names: list[str], top_name: str | None) -> list[int]:
    if not note_names or top_name is None:
        return _stacked_pitches(note_names, 48)
    pitch_classes = [_pitch_class(note_name) for note_name in note_names]
    top_pitch_class = _pitch_class(top_name)
    if top_pitch_class not in pitch_classes:
        return _stacked_pitches(note_names, 48)
    top_pitch = 60 + top_pitch_class
    pitches = []
    for pitch_class in pitch_classes:
        pitch = 60 + pitch_class
        while pitch > top_pitch:
            pitch -= 12
        while pitch + 12 <= top_pitch and pitch_class != top_pitch_class:
            pitch += 12
        pitches.append(pitch)
    return sorted(pitches)


def _random_scale_pitches(label: str, ascending: list[int]) -> list[int]:
    pool = ascending[:-1] or ascending
    generator = random.Random(f"{label}|{','.join(str(pitch) for pitch in ascending)}")
    return [generator.choice(pool) for _index in range(min(12, max(6, len(pool) * 2)))]


def _slash_bass_name(label: str) -> str | None:
    if "/" not in label:
        return None
    return label.split("/", 1)[1]


def _pitch_class(note_name: str) -> int:
    return pitch_class_for_name(note_name) or 0


def _normalized_range(low_pitch: int, high_pitch: int) -> tuple[int, int]:
    low = int(low_pitch)
    high = int(high_pitch)
    return (low, high) if low <= high else (high, low)
