from __future__ import annotations

from bisect import bisect_right

from pitchstems.editor_models import ChordRegion, NoteEvent


class NoteIndex:
    def __init__(self, notes: list[NoteEvent]) -> None:
        self.notes = sorted(notes, key=lambda note: (note.start, note.end, note.stem, note.pitch))
        self.starts = [note.start for note in self.notes]

    def active_at(self, seconds: float) -> list[NoteEvent]:
        end = bisect_right(self.starts, seconds)
        return [note for note in self.notes[:end] if note.end > seconds]

    def overlapping(self, start: float, end: float) -> list[NoteEvent]:
        right = bisect_right(self.starts, end)
        return [note for note in self.notes[:right] if note.end > start]


class ChordIndex:
    def __init__(self, chords: list[ChordRegion], duration: float) -> None:
        self.chords = sorted(chords, key=lambda chord: (chord.start, chord.end))
        self.duration = duration

    def active_at(self, seconds: float) -> ChordRegion | None:
        for chord in self.chords:
            if chord.start <= seconds < chord.end:
                return chord
        return None

    def gap_at(self, seconds: float) -> tuple[float, float] | None:
        if self.active_at(seconds) is not None:
            return None
        previous = max(
            (chord for chord in self.chords if chord.end <= seconds),
            key=lambda chord: chord.end,
            default=None,
        )
        next_chord = min(
            (chord for chord in self.chords if chord.start >= seconds),
            key=lambda chord: chord.start,
            default=None,
        )
        start = previous.end if previous else 0.0
        end = next_chord.start if next_chord else self.duration
        return (start, end) if end - start >= 0.05 else None
