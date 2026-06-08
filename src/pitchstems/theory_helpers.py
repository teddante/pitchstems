from __future__ import annotations

from typing import Any

from pitchstems.chord_analysis import (
    chord_pitch_classes_for_label,
    exact_chord_names_for_pitch_classes,
    midi_velocity_energy,
)
from pitchstems.editor_models import ChordRegion, NoteEvent


def diatonic_chord_labels(analysis: Any) -> list[str]:
    if not analysis.candidates:
        return []
    candidate = analysis.candidates[0]
    intervals = candidate.scale.intervals
    if len(intervals) < 7:
        return []
    labels = []
    for degree_index, interval in enumerate(intervals[:7]):
        root = (candidate.root + interval) % 12
        triad = {
            root,
            (candidate.root + intervals[(degree_index + 2) % 7]) % 12,
            (candidate.root + intervals[(degree_index + 4) % 7]) % 12,
        }
        names = exact_chord_names_for_pitch_classes(triad, bass=root)
        if names:
            labels.append(names[0])
        seventh = {
            *triad,
            (candidate.root + intervals[(degree_index + 6) % 7]) % 12,
        }
        names = exact_chord_names_for_pitch_classes(seventh, bass=root)
        if names:
            labels.append(names[0])
    return labels


def candidate_theory_fit(tones: set[int], analysis: Any) -> float:
    if not tones or not analysis.candidates:
        return 0.0
    scale_tones = {
        (analysis.candidates[0].root + interval) % 12
        for interval in analysis.candidates[0].scale.intervals
    }
    return len(tones & scale_tones) / len(tones)


def candidate_pitch_class_movement(
    tones: set[int],
    previous_chord: ChordRegion | None,
    next_chord: ChordRegion | None,
) -> float:
    scores = []
    for neighbor in [previous_chord, next_chord]:
        if neighbor is None:
            continue
        neighbor_tones = set(chord_pitch_classes_for_label(neighbor.label))
        if neighbor_tones:
            scores.append(_pitch_class_movement_score(neighbor_tones, tones))
    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def _pitch_class_movement_score(from_tones: set[int], to_tones: set[int]) -> float:
    if not from_tones or not to_tones:
        return 0.0
    distances = []
    for pitch_class in from_tones:
        distances.append(min(_pitch_class_distance(pitch_class, target) for target in to_tones))
    average_distance = sum(distances) / len(distances)
    return fit_clamp(1.0 - average_distance / 6.0)


def _pitch_class_distance(first: int, second: int) -> int:
    distance = abs(first - second) % 12
    return min(distance, 12 - distance)


def candidate_common_tones(
    tones: set[int],
    previous_chord: ChordRegion | None,
    next_chord: ChordRegion | None,
) -> float:
    scores = []
    for neighbor in [previous_chord, next_chord]:
        if neighbor is None:
            continue
        neighbor_tones = set(chord_pitch_classes_for_label(neighbor.label))
        if neighbor_tones:
            scores.append(len(tones & neighbor_tones) / len(tones | neighbor_tones))
    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def previous_chord(chords: list[ChordRegion], seconds: float) -> ChordRegion | None:
    previous = [chord for chord in chords if chord.end <= seconds]
    return max(previous, key=lambda chord: chord.end, default=None)


def next_chord(chords: list[ChordRegion], seconds: float) -> ChordRegion | None:
    next_chords = [chord for chord in chords if chord.start >= seconds]
    return min(next_chords, key=lambda chord: chord.start, default=None)


def region_energy(notes: list[NoteEvent], start: float, end: float) -> float:
    total = 0.0
    for note in notes:
        overlap = max(0.0, min(note.end, end) - max(note.start, start))
        if overlap > 0:
            total += overlap * midi_velocity_energy(note.velocity)
    return total


def fit_clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def report_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    minutes = int(seconds // 60)
    remainder = seconds - minutes * 60
    return f"{minutes:02d}:{remainder:06.3f}"
