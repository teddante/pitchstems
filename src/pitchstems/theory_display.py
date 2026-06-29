from __future__ import annotations

from collections.abc import Callable

from pitchstems.notation import pitch_class_for_name, scale_label, spell_scale


def display_theory_note_names(
    note_names: list[str],
    pitch_class_formatter: Callable[[int], str],
) -> list[str]:
    displayed = []
    for note_name in note_names:
        pitch_class = pitch_class_for_name(note_name)
        displayed.append(pitch_class_formatter(pitch_class) if pitch_class is not None else note_name)
    return displayed


def display_scale_candidate_label(candidate, preference: str | None) -> str:
    return scale_label(
        candidate.root,
        candidate.scale.intervals,
        candidate.scale.name,
        preference,
    )


def display_scale_candidate_notes(candidate, preference: str | None) -> list[str]:
    return spell_scale(candidate.root, candidate.scale.intervals, preference)
