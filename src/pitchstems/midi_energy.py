from __future__ import annotations

from pitchstems.editor_models import NoteEvent


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


def point_pitch_energy(notes: list[NoteEvent], seconds: float) -> tuple[dict[int, float], dict[int, float]]:
    pitch_weights: dict[int, float] = {}
    exact_pitch_weights: dict[int, float] = {}
    for note in active_notes_at(notes, seconds):
        weight = midi_velocity_energy(note.velocity)
        pitch_weights[note.pitch % 12] = pitch_weights.get(note.pitch % 12, 0.0) + weight
        exact_pitch_weights[note.pitch] = exact_pitch_weights.get(note.pitch, 0.0) + weight
    return pitch_weights, exact_pitch_weights


def region_pitch_energy(
    notes: list[NoteEvent],
    start: float,
    end: float,
) -> tuple[dict[int, float], dict[int, float]]:
    pitch_weights: dict[int, float] = {}
    exact_pitch_weights: dict[int, float] = {}
    for note in notes:
        overlap = note_overlap_seconds(note, start, end)
        if overlap <= 0:
            continue
        weight = overlap * midi_velocity_energy(note.velocity)
        pitch_weights[note.pitch % 12] = pitch_weights.get(note.pitch % 12, 0.0) + weight
        exact_pitch_weights[note.pitch] = exact_pitch_weights.get(note.pitch, 0.0) + weight
    return pitch_weights, exact_pitch_weights


def total_region_energy(notes: list[NoteEvent], start: float, end: float) -> float:
    pitch_weights, _exact_pitch_weights = region_pitch_energy(notes, start, end)
    return sum(pitch_weights.values())
