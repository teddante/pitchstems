from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pitchstems.audio_clip import AudioClipRange
from pitchstems.separation import StemResult
from pitchstems.transcription import MidiResult


@dataclass(frozen=True)
class PipelineResult:
    project_dir: Path
    normalized_audio: Path
    stems: list[StemResult]
    midi_files: list[MidiResult]
    combined_midi: Path | None
    zip_path: Path | None
    source_audio: Path | None = None
    source_clip: AudioClipRange | None = None
    original_source_audio: Path | None = None
