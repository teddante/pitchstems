from __future__ import annotations

from dataclasses import dataclass

from pitchstems.chord_naming import chord_quality_templates, chord_tones_for_label, display_chord_label
from pitchstems.notation import DEFAULT_PITCH_NAMES, scale_label
from pitchstems.scale_analysis import SCALE_REGISTRY, ScaleDefinition


@dataclass(frozen=True)
class ScaleChord:
    label: str
    notes: list[str]
    degree: str
    category: str
    pitch_classes: tuple[int, ...]


def scale_pitch_classes(root: int, scale: ScaleDefinition) -> tuple[int, ...]:
    return tuple((root + interval) % 12 for interval in scale.intervals)


def contained_chords_for_scale(
    root: int,
    scale: ScaleDefinition,
    spelling_preference: str | None = "auto",
) -> list[ScaleChord]:
    scale_tones = set(scale_pitch_classes(root, scale))
    chords: list[tuple[tuple[int, int, int, str], ScaleChord]] = []
    seen: set[tuple[int, tuple[int, ...], str]] = set()
    for chord_root in scale_pitch_classes(root, scale):
        degree_index = _degree_index(root, scale, chord_root)
        for quality_index, (suffix, intervals) in enumerate(chord_quality_templates()):
            tones = tuple((chord_root + interval) % 12 for interval in intervals)
            tone_set = set(tones)
            if len(tone_set) < 3 or not tone_set <= scale_tones:
                continue
            category = _chord_category(intervals)
            if category == "extended" and len(scale_tones) < 6:
                continue
            key = (chord_root, tuple(sorted(tone_set)), category)
            if key in seen:
                continue
            seen.add(key)
            label = f"{DEFAULT_PITCH_NAMES[chord_root]}{suffix}"
            displayed_label = display_chord_label(label, spelling_preference)
            chords.append(
                (
                    (_category_priority(category), degree_index, len(tone_set), quality_index),
                    ScaleChord(
                        label=displayed_label,
                        notes=chord_tones_for_label(label, spelling_preference),
                        degree=_degree_label(degree_index),
                        category=category,
                        pitch_classes=tuple(sorted(tone_set)),
                    ),
                )
            )
    return [chord for _sort, chord in sorted(chords)]


def searchable_scale_labels(spelling_preference: str | None = "auto") -> list[tuple[str, int, ScaleDefinition]]:
    rows: list[tuple[str, int, ScaleDefinition]] = []
    for root in range(12):
        for scale in SCALE_REGISTRY:
            rows.append((scale_label(root, scale.intervals, scale.name, spelling_preference), root, scale))
    rows.sort(key=lambda row: row[0].lower())
    return rows


def _degree_index(root: int, scale: ScaleDefinition, pitch_class: int) -> int:
    relative = (pitch_class - root) % 12
    try:
        return scale.intervals.index(relative)
    except ValueError:
        return 99


def _degree_label(index: int) -> str:
    return "-" if index >= 99 else str(index + 1)


def _chord_category(intervals: tuple[int, ...]) -> str:
    unique_count = len(set(interval % 12 for interval in intervals))
    if unique_count <= 3:
        return "triad"
    if unique_count == 4 and any(interval % 12 in {9, 10, 11} for interval in intervals):
        return "seventh"
    return "extended"


def _category_priority(category: str) -> int:
    return {"triad": 0, "seventh": 1, "extended": 2}.get(category, 3)
