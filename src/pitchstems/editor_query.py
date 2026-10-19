from __future__ import annotations

from bisect import bisect_left, bisect_right

from pitchstems.review_ranges import MIN_RANGE_SECONDS
from pitchstems.editor_models import ChordRegion, NoteEvent


class NoteIndex:
    def __init__(self, notes: list[NoteEvent]) -> None:
        self.notes = sorted(notes, key=lambda note: (note.start, note.end, note.stem, note.pitch))
        self.starts = [note.start for note in self.notes]
        # No note can still sound later than its start plus the longest duration,
        # so lookups only scan notes that started within that window.
        self.max_duration = max((note.end - note.start for note in self.notes), default=0.0)

    def active_at(self, seconds: float) -> list[NoteEvent]:
        return self.overlapping(seconds, seconds)

    def overlapping(self, start: float, end: float) -> list[NoteEvent]:
        left = bisect_left(self.starts, start - self.max_duration)
        right = bisect_right(self.starts, end)
        return [note for note in self.notes[left:right] if note.end > start]


class ChordIndex:
    def __init__(self, chords: list[ChordRegion], duration: float) -> None:
        self.chords = sorted(chords, key=lambda chord: (chord.start, chord.end))
        self.starts = [chord.start for chord in self.chords]
        self.duration = duration

    def active_at(self, seconds: float) -> ChordRegion | None:
        right = bisect_right(self.starts, seconds)
        for chord in reversed(self.chords[:right]):
            if chord.start <= seconds < chord.end:
                return chord
            if chord.end <= seconds:
                break
        return None

    def previous_before(self, seconds: float) -> ChordRegion | None:
        """Latest-ending chord that finishes at or before ``seconds``."""
        right = bisect_right(self.starts, seconds)
        candidates = [chord for chord in self.chords[:right] if chord.end <= seconds]
        return max(candidates, key=lambda chord: chord.end, default=None)

    def next_after(self, seconds: float) -> ChordRegion | None:
        """Earliest chord that starts at or after ``seconds``."""
        left = bisect_left(self.starts, seconds)
        return self.chords[left] if left < len(self.chords) else None

    def gap_at(self, seconds: float) -> tuple[float, float] | None:
        if self.active_at(seconds) is not None:
            return None
        right = bisect_right(self.starts, seconds)
        previous = None
        for chord in reversed(self.chords[:right]):
            if chord.end <= seconds:
                previous = chord
                break
        next_chord = self.chords[right] if right < len(self.chords) else None
        start = previous.end if previous else 0.0
        end = next_chord.start if next_chord else self.duration
        return (start, end) if end - start >= MIN_RANGE_SECONDS else None
