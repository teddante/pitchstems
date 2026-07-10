from __future__ import annotations

import math
from array import array
from bisect import bisect_right
from dataclasses import dataclass

from pitchstems.editor_project import NoteEvent


@dataclass(frozen=True)
class SynthNote:
    stem: str
    start: float
    end: float
    pitch: int
    velocity: int
    frequency: float
    gain: float


class MidiSynthEngine:
    def __init__(self, notes: list[NoteEvent], duration: float, sample_rate: int = 44_100) -> None:
        self.sample_rate = sample_rate
        self.duration = max(0.0, duration)
        self._notes_by_stem: dict[str, list[SynthNote]] = {}
        self._starts_by_stem: dict[str, list[float]] = {}
        for note in notes:
            if note.end <= note.start:
                continue
            synth_note = SynthNote(
                stem=note.stem,
                start=max(0.0, note.start),
                end=max(0.0, note.end),
                pitch=note.pitch,
                velocity=note.velocity,
                frequency=440.0 * (2 ** ((note.pitch - 69) / 12)),
                gain=min(0.18, max(0.015, note.velocity / 127 * 0.11)),
            )
            self._notes_by_stem.setdefault(note.stem, []).append(synth_note)

        for stem, stem_notes in self._notes_by_stem.items():
            stem_notes.sort(key=lambda item: item.start)
            self._starts_by_stem[stem] = [item.start for item in stem_notes]

    @property
    def has_notes(self) -> bool:
        return bool(self._notes_by_stem)

    def render(self, position_seconds: float, frame_count: int, track_volumes: dict[str, float]) -> bytes:
        if frame_count <= 0:
            return b""
        samples = array("f", [0.0]) * frame_count
        buffer_start = max(0.0, position_seconds)
        buffer_end = buffer_start + frame_count / self.sample_rate
        for stem, volume in track_volumes.items():
            if volume <= 0:
                continue
            self._add_stem(samples, stem, volume, buffer_start, buffer_end)
        return _pcm16(samples)

    def _add_stem(
        self,
        samples: array,
        stem: str,
        volume: float,
        buffer_start: float,
        buffer_end: float,
    ) -> None:
        notes = self._notes_by_stem.get(stem)
        starts = self._starts_by_stem.get(stem)
        if not notes or not starts:
            return
        limit = bisect_right(starts, buffer_end)
        for note_index in range(limit):
            note = notes[note_index]
            if note.end <= buffer_start:
                continue
            _add_note(samples, note, volume, buffer_start, self.sample_rate)


def _add_note(samples: array, note: SynthNote, volume: float, buffer_start: float, sample_rate: int) -> None:
    start = max(0, int((note.start - buffer_start) * sample_rate))
    end = min(len(samples), max(start + 1, int(math.ceil((note.end - buffer_start) * sample_rate))))
    if end <= 0 or start >= len(samples):
        return
    start = max(0, start)
    phase_step = (2 * math.pi * note.frequency) / sample_rate
    attack = max(1, int(0.01 * sample_rate))
    release = max(1, int(0.04 * sample_rate))
    for index in range(start, end):
        note_frame = int((buffer_start - note.start) * sample_rate) + index
        remaining = int((note.end - buffer_start) * sample_rate) - index
        envelope = min(1.0, max(0.0, note_frame / attack), max(0.0, remaining / release))
        value = (
            math.sin(phase_step * note_frame) * 0.82
            + math.sin(phase_step * 2 * note_frame) * 0.18
        )
        samples[index] += value * note.gain * volume * max(0.0, envelope)


def _pcm16(samples: array) -> bytes:
    return array("h", (int(_soft_clip(sample) * 32767) for sample in samples)).tobytes()


def _soft_clip(value: float) -> float:
    return math.tanh(value * 0.95)
