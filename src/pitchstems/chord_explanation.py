"""Chord explanation helpers and compatibility exports."""

from __future__ import annotations

from pitchstems.chord_naming import PITCH_NAMES
from pitchstems.chord_scoring import (
    _interval_names,
    _interval_quality_name,
    _ordered_pitch_classes,
    _partial_chord_completions,
    _perfect_fifth_root,
)

__all__ = [
    "partial_harmony_hints",
    "_interval_names",
    "_interval_quality_name",
    "_ordered_pitch_classes",
]


def partial_harmony_hints(
    pitch_classes: set[int],
    bass: int | None = None,
    required_pitch_classes: set[int] | None = None,
    excluded_pitch_classes: set[int] | None = None,
) -> list[str]:
    observed = set(pitch_classes)
    if required_pitch_classes:
        observed |= required_pitch_classes
    if excluded_pitch_classes:
        observed -= excluded_pitch_classes
    if not observed:
        return []

    ordered = _ordered_pitch_classes(observed, bass)
    hints = [f"Detected note set: {' - '.join(PITCH_NAMES[pitch_class] for pitch_class in ordered)}."]
    if len(observed) == 1:
        hints.append("Single note only: not enough harmonic evidence to name a chord.")
        return hints
    if len(observed) == 2:
        root = bass if bass in observed else ordered[0]
        other = next(pitch_class for pitch_class in ordered if pitch_class != root)
        interval = (other - root) % 12
        hints.append(
            f"Two-note interval: {PITCH_NAMES[root]} - {PITCH_NAMES[other]} "
            f"({_interval_quality_name(interval)} above {PITCH_NAMES[root]})."
        )
        fifth_root = _perfect_fifth_root(observed, root)
        if fifth_root is not None:
            hints.append(
                f"Power-chord shell: {PITCH_NAMES[fifth_root]}5 "
                f"({PITCH_NAMES[fifth_root]} - {PITCH_NAMES[(fifth_root + 7) % 12]})."
            )

    completions = _partial_chord_completions(
        observed,
        bass,
        required_pitch_classes=required_pitch_classes,
        excluded_pitch_classes=excluded_pitch_classes,
    )
    if completions:
        hints.append(f"Possible incomplete chord names: {', '.join(completions)}.")
    return hints
