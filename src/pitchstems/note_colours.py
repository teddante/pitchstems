from __future__ import annotations

from pitchstems.notation import pitch_class_for_name

NOTE_ROLE_COLOURS = (
    "#f97316",
    "#2563eb",
    "#16a34a",
    "#dc2626",
    "#7c3aed",
    "#0891b2",
    "#ca8a04",
    "#db2777",
    "#65a30d",
    "#9333ea",
    "#0d9488",
    "#ea580c",
)


def note_colour_map(note_names: list[str], root_pitch_class: int | None = None) -> dict[int, str]:
    pitch_classes = [
        pitch_class
        for note_name in note_names
        for pitch_class in [pitch_class_for_name(note_name)]
        if pitch_class is not None
    ]
    ordered = _dedupe_pitch_classes(pitch_classes)
    if root_pitch_class is not None and root_pitch_class % 12 in ordered:
        root = root_pitch_class % 12
        root_index = ordered.index(root)
        ordered = ordered[root_index:] + ordered[:root_index]
    return {
        pitch_class: NOTE_ROLE_COLOURS[index % len(NOTE_ROLE_COLOURS)]
        for index, pitch_class in enumerate(ordered)
    }


def _dedupe_pitch_classes(pitch_classes: list[int]) -> list[int]:
    ordered: list[int] = []
    for pitch_class in pitch_classes:
        pitch_class %= 12
        if pitch_class not in ordered:
            ordered.append(pitch_class)
    return ordered
