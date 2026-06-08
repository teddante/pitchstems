from __future__ import annotations

from pitchstems.notation import (
    DEFAULT_PITCH_NAMES,
    pitch_class_for_name,
    pitch_class_name,
    respell_chord_label,
    spell_chord_tones,
    split_chord_label,
)

PITCH_NAMES = DEFAULT_PITCH_NAMES


def display_chord_label(label: str, spelling_preference: str | None = "auto") -> str:
    return respell_chord_label(label, spelling_preference)


def chord_bass_name_for_label(label: str, spelling_preference: str | None = "auto") -> str | None:
    parts = split_chord_label(label)
    if parts is None or parts.bass_pitch_class is None:
        return None
    return pitch_class_name(parts.bass_pitch_class, spelling_preference)


def chord_tones_for_label(label: str, spelling_preference: str | None = "auto") -> list[str]:
    base_label = label.split("/", 1)[0]
    root_name = next(
        (
            name
            for name in sorted(_accepted_note_names(), key=len, reverse=True)
            if base_label.startswith(name)
        ),
        None,
    )
    if root_name is None:
        return [PITCH_NAMES[pitch_class] for pitch_class in chord_pitch_classes_for_label(label)]
    suffix = base_label[len(root_name):]
    omitted_intervals: set[int] = set()
    if "(no" in suffix:
        suffix, omitted_intervals = _split_omitted_suffix(suffix)
    quality = next(
        (
            intervals
            for quality_suffix, intervals in _chord_qualities()
            if quality_suffix == suffix
        ),
        None,
    )
    if quality is None:
        return [PITCH_NAMES[pitch_class] for pitch_class in chord_pitch_classes_for_label(label)]
    intervals = [interval for interval in quality if interval not in omitted_intervals]
    return spell_chord_tones(label, intervals, spelling_preference)


def alternate_chord_names_for_label(label: str, bass: int | None = None) -> list[str]:
    pitch_classes = set(chord_pitch_classes_for_label(label))
    if not pitch_classes:
        return []
    return [
        alias
        for alias in exact_chord_names_for_pitch_classes(pitch_classes, bass)
        if alias != label
    ]


def exact_chord_names_for_pitch_classes(pitch_classes: set[int], bass: int | None = None) -> list[str]:
    names: list[str] = []
    for root in range(12):
        for suffix, intervals in _chord_qualities():
            tones = {(root + interval) % 12 for interval in intervals}
            if tones != pitch_classes:
                continue
            label = f"{PITCH_NAMES[root]}{suffix}"
            if bass is not None and bass != root:
                label = f"{label}/{PITCH_NAMES[bass]}"
            names.append(label)
    return names


def chord_pitch_classes_for_label(label: str) -> list[int]:
    base_label = label.split("/", 1)[0]
    root_name = next(
        (
            name
            for name in sorted(_accepted_note_names(), key=len, reverse=True)
            if base_label.startswith(name)
        ),
        None,
    )
    if root_name is None:
        return []
    suffix = base_label[len(root_name):]
    omitted_intervals: set[int] = set()
    if "(no" in suffix:
        suffix, omitted_intervals = _split_omitted_suffix(suffix)
    quality = next(
        (
            intervals
            for quality_suffix, intervals in _chord_qualities()
            if quality_suffix == suffix
        ),
        None,
    )
    if quality is None:
        return []
    root = pitch_class_for_name(root_name)
    if root is None:
        return []
    tones: list[int] = []
    for interval in quality:
        if interval in omitted_intervals:
            continue
        pitch_class = (root + interval) % 12
        if pitch_class not in tones:
            tones.append(pitch_class)
    return tones


def _accepted_note_names() -> tuple[str, ...]:
    return (
        "C#",
        "Db",
        "D#",
        "Eb",
        "E#",
        "Fb",
        "F#",
        "Gb",
        "G#",
        "Ab",
        "A#",
        "Bb",
        "B#",
        "Cb",
        "C",
        "D",
        "E",
        "F",
        "G",
        "A",
        "B",
    )


def _split_omitted_suffix(suffix: str) -> tuple[str, set[int]]:
    omitted_intervals: set[int] = set()
    base = suffix
    while "(no" in base:
        start = base.find("(no")
        end = base.find(")", start)
        if end < 0:
            break
        token = base[start + 3:end]
        if token == "3":
            omitted_intervals.update({3, 4})
        elif token == "5":
            omitted_intervals.add(7)
        base = f"{base[:start]}{base[end + 1:]}"
    return base, omitted_intervals


def _chord_qualities() -> list[tuple[str, tuple[int, ...]]]:
    return [
        ("maj9(no3)", (0, 7, 11, 2)),
        ("9(no3)", (0, 7, 10, 2)),
        ("maj9", (0, 4, 7, 11, 2)),
        ("9", (0, 4, 7, 10, 2)),
        ("m9", (0, 3, 7, 10, 2)),
        ("maj7sus2", (0, 2, 7, 11)),
        ("7sus2", (0, 2, 7, 10)),
        ("maj7", (0, 4, 7, 11)),
        ("7", (0, 4, 7, 10)),
        ("m7", (0, 3, 7, 10)),
        ("mMaj7", (0, 3, 7, 11)),
        ("m7b5", (0, 3, 6, 10)),
        ("dim7", (0, 3, 6, 9)),
        ("6", (0, 4, 7, 9)),
        ("m6", (0, 3, 7, 9)),
        ("add9", (0, 4, 7, 2)),
        ("madd9", (0, 3, 7, 2)),
        ("add4", (0, 4, 5, 7)),
        ("add11", (0, 4, 7, 5)),
        ("7sus4", (0, 5, 7, 10)),
        ("sus2", (0, 2, 7)),
        ("add9(no3)", (0, 7, 2)),
        ("sus4", (0, 5, 7)),
        ("dim", (0, 3, 6)),
        ("aug", (0, 4, 8)),
        ("m", (0, 3, 7)),
        ("", (0, 4, 7)),
    ]
