"""Chord explanation helpers and compatibility exports."""

from __future__ import annotations

from pitchstems.chord_naming import PITCH_NAMES

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
    from pitchstems.chord_analysis import partial_harmony_hints as _partial_harmony_hints

    return _partial_harmony_hints(
        pitch_classes,
        bass=bass,
        required_pitch_classes=required_pitch_classes,
        excluded_pitch_classes=excluded_pitch_classes,
    )


def _ordered_pitch_classes(pitch_classes: set[int], root: int | None = None) -> list[int]:
    if root is None or root not in pitch_classes:
        return sorted(pitch_classes)
    return sorted(pitch_classes, key=lambda pitch_class: (pitch_class - root) % 12)


def _interval_quality_name(interval: int) -> str:
    return {
        0: "unison",
        1: "minor second",
        2: "major second",
        3: "minor third",
        4: "major third",
        5: "perfect fourth",
        6: "tritone",
        7: "perfect fifth",
        8: "minor sixth",
        9: "major sixth",
        10: "minor seventh",
        11: "major seventh",
    }[interval % 12]


def _interval_names(root: int, intervals) -> list[str]:
    return [PITCH_NAMES[(root + interval) % 12] for interval in intervals]
