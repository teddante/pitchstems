from __future__ import annotations

import math
from array import array
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from typing import Any

from pitchstems.editor_models import NoteEvent

# The live synth runs in Qt's pull-mode audio callback on the GUI thread. NumPy
# (installed with the ML extras) renders it ~18x faster than the per-sample
# Python fallback, which stays for GUI-only installs.
_np: Any
try:
    import numpy as _np
except ImportError:  # pragma: no cover - exercised by forcing the fallback in tests
    _np = None


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
        self._max_duration_by_stem: dict[str, float] = {}
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
            self._max_duration_by_stem[stem] = max(item.end - item.start for item in stem_notes)

    @property
    def has_notes(self) -> bool:
        return bool(self._notes_by_stem)

    @property
    def stems(self) -> list[str]:
        return list(self._notes_by_stem)

    def render(self, position_seconds: float, frame_count: int, track_volumes: dict[str, float]) -> bytes:
        if frame_count <= 0:
            return b""
        if _np is not None:
            buffer = self._render_numpy(position_seconds, frame_count, track_volumes)
            return (_np.tanh(buffer * 0.95) * 32767).astype(_np.int16).tobytes()
        return _pcm16(self._render_python(position_seconds, frame_count, track_volumes))

    def render_samples(self, position_seconds: float, frame_count: int, track_volumes: dict[str, float]) -> array:
        if _np is None:
            return self._render_python(position_seconds, frame_count, track_volumes)
        samples = array("f")
        samples.frombytes(
            self._render_numpy(position_seconds, frame_count, track_volumes).astype(_np.float32).tobytes()
        )
        return samples

    def _render_python(self, position_seconds: float, frame_count: int, track_volumes: dict[str, float]) -> array:
        samples = array("f", [0.0]) * max(0, frame_count)
        for note, volume, buffer_start in self._sounding_notes(position_seconds, frame_count, track_volumes):
            _add_note(samples, note, volume, buffer_start, self.sample_rate)
        return samples

    def _render_numpy(self, position_seconds: float, frame_count: int, track_volumes: dict[str, float]) -> Any:
        samples = _np.zeros(max(0, frame_count), dtype=_np.float64)
        for note, volume, buffer_start in self._sounding_notes(position_seconds, frame_count, track_volumes):
            _add_note_numpy(samples, note, volume, buffer_start, self.sample_rate)
        return samples

    def _sounding_notes(
        self,
        position_seconds: float,
        frame_count: int,
        track_volumes: dict[str, float],
    ) -> list[tuple[SynthNote, float, float]]:
        buffer_start = max(0.0, position_seconds)
        buffer_end = buffer_start + max(0, frame_count) / self.sample_rate
        sounding: list[tuple[SynthNote, float, float]] = []
        for stem, volume in track_volumes.items():
            notes = self._notes_by_stem.get(stem)
            starts = self._starts_by_stem.get(stem)
            if volume <= 0 or not notes or not starts:
                continue
            # Notes that started before this window minus the longest note cannot overlap it.
            first = bisect_left(starts, buffer_start - self._max_duration_by_stem[stem])
            limit = bisect_right(starts, buffer_end)
            for note in notes[first:limit]:
                if note.end > buffer_start:
                    sounding.append((note, volume, buffer_start))
        return sounding


def _add_note(samples: array, note: SynthNote, volume: float, buffer_start: float, sample_rate: int) -> None:
    bounds = _note_bounds(len(samples), note, buffer_start, sample_rate)
    if bounds is None:
        return
    start, end = bounds
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


def _note_bounds(frame_count: int, note: SynthNote, buffer_start: float, sample_rate: int) -> tuple[int, int] | None:
    start = max(0, int((note.start - buffer_start) * sample_rate))
    end = min(frame_count, max(start + 1, math.ceil((note.end - buffer_start) * sample_rate)))
    if end <= 0 or start >= frame_count:
        return None
    return start, end


def _add_note_numpy(samples: Any, note: SynthNote, volume: float, buffer_start: float, sample_rate: int) -> None:
    bounds = _note_bounds(len(samples), note, buffer_start, sample_rate)
    if bounds is None:
        return
    start, end = bounds
    phase_step = (2 * math.pi * note.frequency) / sample_rate
    attack = max(1, int(0.01 * sample_rate))
    release = max(1, int(0.04 * sample_rate))
    index = _np.arange(start, end)
    note_frame = int((buffer_start - note.start) * sample_rate) + index
    remaining = int((note.end - buffer_start) * sample_rate) - index
    envelope = _np.minimum(
        _np.minimum(1.0, _np.maximum(0.0, note_frame / attack)),
        _np.maximum(0.0, remaining / release),
    )
    value = _np.sin(phase_step * note_frame) * 0.82 + _np.sin(phase_step * 2 * note_frame) * 0.18
    samples[start:end] += value * (note.gain * volume) * _np.maximum(0.0, envelope)


def _pcm16(samples: array) -> bytes:
    return array("h", (int(_soft_clip(sample) * 32767) for sample in samples)).tobytes()


def _soft_clip(value: float) -> float:
    return math.tanh(value * 0.95)
