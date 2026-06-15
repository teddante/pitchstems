from __future__ import annotations

import contextlib
import logging
import wave
from bisect import bisect_right
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from mido import MidiFile, tick2second

from pitchstems.chord_analysis import (
    ChordAnalysis,
    PITCH_NAMES,
    alternate_chord_names_for_label,
    chord_bass_name_for_label,
    chord_pitch_classes_for_label,
    chord_tones_for_label,
    display_chord_label,
    exact_chord_names_for_pitch_classes,
    identify_chord,
    midi_note_name,
)
from pitchstems.chord_detection import (
    active_notes_at,
    analyze_chord,
    analyze_chord_at,
    analyze_chord_region,
    detect_chords,
    midi_velocity_energy,
)
from pitchstems.chord_explanation import partial_harmony_hints
from pitchstems.chord_scoring import ChordScoringOptions, PartialChordCandidate
from pitchstems.editor_models import ChordRegion, NoteEvent
from pitchstems.editor_query import ChordIndex, NoteIndex
from pitchstems.pipeline import PipelineResult


DEFAULT_TEMPO = 500000
LOGGER = logging.getLogger(__name__)

__all__ = [
    "ChordAnalysis",
    "ChordRegion",
    "ChordScoringOptions",
    "EditorProject",
    "EditorTrack",
    "NoteEvent",
    "PITCH_NAMES",
    "PartialChordCandidate",
    "active_notes_at",
    "alternate_chord_names_for_label",
    "analyze_chord",
    "analyze_chord_at",
    "analyze_chord_region",
    "build_editor_project",
    "chord_bass_name_for_label",
    "chord_pitch_classes_for_label",
    "chord_tones_for_label",
    "detect_chords",
    "display_chord_label",
    "exact_chord_names_for_pitch_classes",
    "identify_chord",
    "midi_note_name",
    "midi_velocity_energy",
    "partial_harmony_hints",
    "read_midi_notes",
]


@dataclass(frozen=True)
class EditorTrack:
    name: str
    audio_path: Path
    muted: bool = False
    solo: bool = False


@dataclass(frozen=True)
class EditorProject:
    project_dir: Path
    source_audio: Path
    tracks: list[EditorTrack]
    notes: list[NoteEvent]
    chords: list[ChordRegion]
    duration: float

    @cached_property
    def note_index(self) -> NoteIndex:
        return NoteIndex(self.notes)

    @cached_property
    def chord_index(self) -> ChordIndex:
        return ChordIndex(self.chords, self.duration)


def build_editor_project(result: PipelineResult) -> EditorProject:
    """Build the first editable timeline model from a completed pipeline result."""
    tracks = [EditorTrack(name=stem.name, audio_path=stem.path) for stem in result.stems]
    notes: list[NoteEvent] = []
    for midi in result.midi_files:
        notes.extend(_read_midi_notes_for_project(midi.path, midi.stem))
    notes.sort(key=lambda note: (note.start, note.stem, note.pitch, note.end))
    duration = max(
        [note.end for note in notes]
        + [_audio_duration_seconds(track.audio_path) for track in tracks]
        + [_audio_duration_seconds(result.normalized_audio), 0.0]
    )
    chords = detect_chords(notes)
    return EditorProject(
        project_dir=result.project_dir,
        source_audio=result.normalized_audio,
        tracks=tracks,
        notes=notes,
        chords=chords,
        duration=duration,
    )


def _read_midi_notes_for_project(path: Path, stem: str) -> list[NoteEvent]:
    try:
        return read_midi_notes(path, stem)
    except Exception as exc:
        LOGGER.warning("Skipping unreadable MIDI file for %s: %s (%s)", stem, path, exc)
        return []


def _audio_duration_seconds(path: Path) -> float:
    with contextlib.suppress(OSError, wave.Error, EOFError):
        with wave.open(str(path), "rb") as audio:
            frame_rate = audio.getframerate()
            if frame_rate > 0:
                return audio.getnframes() / frame_rate
    return 0.0


def read_midi_notes(path: Path, stem: str) -> list[NoteEvent]:
    """Read note on/off events from a MIDI file into absolute seconds."""
    midi = MidiFile(path)
    tempo_map = _tempo_map(midi)
    tempo_ticks = [tick for tick, _tempo, _seconds in tempo_map]
    notes: list[NoteEvent] = []

    for track in midi.tracks:
        ticks = 0
        active: dict[int, list[tuple[float, int]]] = {}
        for message in track:
            ticks += message.time
            seconds = _ticks_to_seconds(ticks, tempo_map, tempo_ticks, midi.ticks_per_beat)
            if message.type == "set_tempo":
                continue
            if message.type == "note_on" and message.velocity > 0:
                active.setdefault(message.note, []).append((seconds, message.velocity))
                continue
            if message.type in {"note_off", "note_on"}:
                starts = active.get(message.note)
                if not starts:
                    continue
                start, velocity = starts.pop(0)
                if seconds > start:
                    notes.append(
                        NoteEvent(
                            stem=stem,
                            start=start,
                            end=seconds,
                            pitch=message.note,
                            velocity=velocity,
                        )
                    )
    return notes


def _tempo_map(midi: MidiFile) -> list[tuple[int, int, float]]:
    tempo_events: list[tuple[int, int]] = []
    for track in midi.tracks:
        ticks = 0
        for message in track:
            ticks += message.time
            if message.type == "set_tempo":
                tempo_events.append((ticks, message.tempo))

    tempo_events.sort(key=lambda item: item[0])
    current_tempo = DEFAULT_TEMPO
    last_tick = 0
    seconds = 0.0
    segments: list[tuple[int, int, float]] = [(0, current_tempo, 0.0)]
    for tick, tempo in tempo_events:
        if tick > last_tick:
            seconds += tick2second(tick - last_tick, midi.ticks_per_beat, current_tempo)
            last_tick = tick
        current_tempo = tempo
        if segments[-1][0] == tick:
            segments[-1] = (tick, current_tempo, seconds)
        else:
            segments.append((tick, current_tempo, seconds))
    return segments


def _ticks_to_seconds(
    ticks: int,
    tempo_map: list[tuple[int, int, float]],
    tempo_ticks: list[int],
    ticks_per_beat: int,
) -> float:
    index = max(0, bisect_right(tempo_ticks, ticks) - 1)
    segment_tick, tempo, segment_seconds = tempo_map[index]
    return segment_seconds + tick2second(ticks - segment_tick, ticks_per_beat, tempo)
