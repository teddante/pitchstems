from __future__ import annotations

from collections.abc import Iterable

from pitchstems.editor_models import NoteEvent

PitchEnergy = tuple[dict[int, float], dict[int, float]]


def active_notes_at(notes: list[NoteEvent], seconds: float) -> list[NoteEvent]:
    return sorted(
        [note for note in notes if note.start <= seconds < note.end],
        key=lambda note: (note.pitch, note.stem),
    )


def note_overlap_seconds(note: NoteEvent, start: float, end: float) -> float:
    return max(0.0, min(note.end, end) - max(note.start, start))


def midi_velocity_energy(velocity: int) -> float:
    amplitude = max(0, min(velocity, 127)) / 127
    return amplitude * amplitude


def point_pitch_energy(notes: list[NoteEvent], seconds: float) -> PitchEnergy:
    """Velocity energy per pitch class and per exact pitch for notes sounding at ``seconds``."""
    return _accumulate(
        (note, midi_velocity_energy(note.velocity)) for note in active_notes_at(notes, seconds)
    )


def region_pitch_energy(notes: list[NoteEvent], start: float, end: float) -> PitchEnergy:
    """Velocity energy weighted by overlap seconds for notes inside ``start``-``end``."""
    return ranges_pitch_energy(notes, [(start, end)])


def ranges_pitch_energy(notes: list[NoteEvent], ranges: Iterable[tuple[float, float]]) -> PitchEnergy:
    """Summed overlap-weighted energy across several (possibly reversed) time ranges."""
    weighted = []
    for start, end in ranges:
        start, end = sorted((start, end))
        if end - start <= 0:
            continue
        for note in notes:
            overlap = note_overlap_seconds(note, start, end)
            if overlap > 0:
                weighted.append((note, overlap * midi_velocity_energy(note.velocity)))
    return _accumulate(weighted)


def total_region_energy(notes: list[NoteEvent], start: float, end: float) -> float:
    pitch_weights, _exact_pitch_weights = region_pitch_energy(notes, start, end)
    return sum(pitch_weights.values())


def _accumulate(weighted_notes: Iterable[tuple[NoteEvent, float]]) -> PitchEnergy:
    pitch_weights: dict[int, float] = {}
    exact_pitch_weights: dict[int, float] = {}
    for note, weight in weighted_notes:
        pitch_weights[note.pitch % 12] = pitch_weights.get(note.pitch % 12, 0.0) + weight
        exact_pitch_weights[note.pitch] = exact_pitch_weights.get(note.pitch, 0.0) + weight
    return pitch_weights, exact_pitch_weights
