from __future__ import annotations

from dataclasses import dataclass

from pitchstems.notation import midi_note_name


@dataclass(frozen=True)
class NoteEvent:
    stem: str
    start: float
    end: float
    pitch: int
    velocity: int

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    @property
    def name(self) -> str:
        return midi_note_name(self.pitch)


@dataclass(frozen=True)
class ChordRegion:
    start: float
    end: float
    label: str
    confidence: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)
