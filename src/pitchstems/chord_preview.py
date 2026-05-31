from __future__ import annotations

from pitchstems.notation import pitch_class_for_name


def chord_preview_pitches(label: str, note_names: list[str]) -> list[int]:
    pitches = []
    previous = None
    for note_name in note_names:
        pitch_class = _pitch_class(note_name)
        pitch = 48 + pitch_class
        while previous is not None and pitch <= previous:
            pitch += 12
        pitches.append(pitch)
        previous = pitch
    if "/" in label:
        bass_name = label.split("/", 1)[1]
        bass_pitch = 36 + _pitch_class(bass_name)
        pitches.insert(0, bass_pitch)
    return pitches


def _pitch_class(note_name: str) -> int:
    return pitch_class_for_name(note_name) or 0
