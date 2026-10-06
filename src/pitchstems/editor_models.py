from __future__ import annotations

from dataclasses import dataclass

from pitchstems.notation import midi_note_name


def _duration(start: float, end: float) -> float:
    return max(0.0, end - start)


class TimeSpanMixin:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return _duration(self.start, self.end)


@dataclass(frozen=True)
class NoteEvent(TimeSpanMixin):
    stem: str
    start: float
    end: float
    pitch: int
    velocity: int

    @property
    def name(self) -> str:
        return midi_note_name(self.pitch)


@dataclass(frozen=True)
class ChordRegion(TimeSpanMixin):
    start: float
    end: float
    label: str
    confidence: float
