from __future__ import annotations

from pitchstems.editor_models import NoteEvent
from pitchstems.notation import pitch_class_for_name


def chord_preview_pitches(
    label: str,
    note_names: list[str],
    *,
    bass_name: str | None = None,
    top_name: str | None = None,
    low_pitch: int | None = None,
    high_pitch: int | None = None,
) -> list[int]:
    if low_pitch is not None and high_pitch is not None:
        return _ranged_pitches(label, note_names, bass_name, low_pitch, high_pitch)
    pitches = _top_voiced_pitches(note_names, top_name) if top_name else _stacked_pitches(note_names)
    bass = bass_name or _slash_bass_name(label)
    if bass:
        bass_pitch = 36 + _pitch_class(bass)
        pitches.insert(0, bass_pitch)
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
        NoteEvent(
            stem="official-chord",
            start=0.0,
            end=1.45,
            pitch=pitch,
            velocity=92,
        )
        for pitch in chord_preview_pitches(
            label,
            note_names,
            bass_name=bass_name,
            top_name=top_name,
            low_pitch=low_pitch,
            high_pitch=high_pitch,
        )
    ]


def _ranged_pitches(
    label: str,
    note_names: list[str],
    bass_name: str | None,
    low_pitch: int,
    high_pitch: int,
) -> list[int]:
    low, high = _normalized_range(low_pitch, high_pitch)
    pitch_classes = {_pitch_class(note_name) for note_name in note_names}
    bass = bass_name or _slash_bass_name(label)
    if bass:
        pitch_classes.add(_pitch_class(bass))
    pitches = [
        pitch
        for pitch in range(low, high + 1)
        if pitch % 12 in pitch_classes
    ]
    if pitches:
        return pitches
    return [
        min(max(_stacked_pitches(note_names)[0], low), high)
    ] if note_names else []


def _stacked_pitches(note_names: list[str]) -> list[int]:
    pitches = []
    previous = None
    for note_name in note_names:
        pitch_class = _pitch_class(note_name)
        pitch = 48 + pitch_class
        while previous is not None and pitch <= previous:
            pitch += 12
        pitches.append(pitch)
        previous = pitch
    return pitches


def _top_voiced_pitches(note_names: list[str], top_name: str | None) -> list[int]:
    if not note_names or top_name is None:
        return _stacked_pitches(note_names)
    pitch_classes = [_pitch_class(note_name) for note_name in note_names]
    top_pitch_class = _pitch_class(top_name)
    if top_pitch_class not in pitch_classes:
        return _stacked_pitches(note_names)
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
