from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pitchstems.audio_clip import AudioClipRange
from pitchstems.filename_safety import safe_stem_key


@dataclass(frozen=True)
class StemResult:
    name: str
    path: Path
    stem_id: str | None = None

    @property
    def safe_key(self) -> str:
        return safe_stem_key(self.stem_id or self.name)


@dataclass(frozen=True)
class MidiResult:
    stem: str
    path: Path
    stem_id: str | None = None

    @property
    def safe_key(self) -> str:
        return safe_stem_key(self.stem_id or self.stem)


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
    settings: dict[str, Any] = field(default_factory=dict)
