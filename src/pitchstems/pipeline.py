from __future__ import annotations

import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from pitchstems.audio import normalize_to_wav
from pitchstems.midi import combine_midi_tracks
from pitchstems.separation import SeparationOptions, StemResult, separate_stems
from pitchstems.transcription import MidiOptions, MidiResult, transcribe_stem_to_midi


@dataclass(frozen=True)
class PipelineResult:
    project_dir: Path
    normalized_audio: Path
    stems: list[StemResult]
    midi_files: list[MidiResult]
    combined_midi: Path | None
    zip_path: Path | None


def process_audio_file(
    input_path: Path,
    output_root: Path,
    quality: str = "song-6-stem",
    separation_options: SeparationOptions | None = None,
    generate_midi: bool = True,
    midi_policy: str = "pitched",
    midi_options: MidiOptions | None = None,
    midi_stems: set[str] | None = None,
    create_zip: bool = True,
    log: Callable[[str], None] | None = None,
) -> PipelineResult:
    """Run the complete local stem-to-MIDI pipeline."""
    input_path = input_path.expanduser().resolve()
    output_root = output_root.expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    project_dir = _project_dir(output_root, input_path)
    work_dir = project_dir / "work"
    stems_dir = project_dir / "stems"
    midi_dir = project_dir / "midi"
    export_dir = project_dir / "export"

    for directory in [work_dir, stems_dir, midi_dir, export_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    if log:
        log(f"Preparing {input_path.name}...")
        log("Audio prep: FFmpeg -> stereo 44.1 kHz PCM WAV for native BS-RoFormer.")
    normalized_audio = normalize_to_wav(input_path, work_dir / f"{input_path.stem}.wav")

    stems = separate_stems(normalized_audio, stems_dir, profile=quality, options=separation_options, log=log)

    for stem in stems:
        shutil.copy2(stem.path, export_dir / stem.path.name)

    midi_files: list[MidiResult] = []
    combined_midi = None
    zip_path = None
    if generate_midi and midi_policy != "none":
        midi_result = process_midi_from_stems(
            project_dir=project_dir,
            input_stem=input_path.stem,
            normalized_audio=normalized_audio,
            stems=stems,
            midi_policy=midi_policy,
            midi_options=midi_options,
            midi_stems=midi_stems,
            create_zip=create_zip,
            log=log,
        )
        midi_files = midi_result.midi_files
        combined_midi = midi_result.combined_midi
        zip_path = midi_result.zip_path
    else:
        if log:
            log("Skipping MIDI transcription.")
        zip_path = _zip_export(export_dir, project_dir / f"{input_path.stem}_pitchstems.zip") if create_zip else None

    if log:
        log(f"Done: {zip_path or export_dir}")

    return PipelineResult(
        project_dir=project_dir,
        normalized_audio=normalized_audio,
        stems=stems,
        midi_files=midi_files,
        combined_midi=combined_midi,
        zip_path=zip_path,
    )


def process_midi_from_stems(
    project_dir: Path,
    input_stem: str,
    normalized_audio: Path | None,
    stems: list[StemResult],
    midi_policy: str = "pitched",
    midi_options: MidiOptions | None = None,
    midi_stems: set[str] | None = None,
    create_zip: bool = True,
    log: Callable[[str], None] | None = None,
) -> PipelineResult:
    """Run or rerun Basic Pitch from already separated stems."""
    project_dir = project_dir.expanduser().resolve()
    midi_dir = project_dir / "midi"
    export_dir = project_dir / "export"
    midi_dir.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)

    _clear_midi_outputs(midi_dir, export_dir)

    midi_files: list[MidiResult] = []
    selected_midi_stems = {stem.lower() for stem in midi_stems} if midi_stems is not None else None
    skip_percussion = midi_policy != "all" and selected_midi_stems is None
    if log:
        log("Running Basic Pitch from existing separated stems.")

    for stem in stems:
        if selected_midi_stems is not None and stem.name.lower() not in selected_midi_stems:
            if log:
                log(f"Skipping MIDI for {stem.name}: not selected for Basic Pitch analysis.")
            continue
        midi = transcribe_stem_to_midi(
            stem.name,
            stem.path,
            midi_dir / stem.name,
            skip_percussion=skip_percussion,
            options=midi_options,
            log=log,
        )
        if midi:
            midi_files.append(midi)

    combined_midi = combine_midi_tracks(midi_files, export_dir / f"{input_stem}_combined.mid")
    for midi in midi_files:
        shutil.copy2(midi.path, export_dir / f"{midi.stem}.mid")

    zip_path = _zip_export(export_dir, project_dir / f"{input_stem}_pitchstems.zip") if create_zip else None
    if log:
        log(f"MIDI stage done: {zip_path or export_dir}")

    return PipelineResult(
        project_dir=project_dir,
        normalized_audio=normalized_audio or project_dir / "work" / f"{input_stem}.wav",
        stems=stems,
        midi_files=midi_files,
        combined_midi=combined_midi,
        zip_path=zip_path,
    )


def _project_dir(output_root: Path, input_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_name = "".join(char if char.isalnum() or char in "-_" else "_" for char in input_path.stem)
    return output_root / f"{safe_name}-{timestamp}"


def _zip_export(export_dir: Path, zip_path: Path) -> Path:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(export_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(export_dir))
    return zip_path


def _clear_midi_outputs(midi_dir: Path, export_dir: Path) -> None:
    if midi_dir.exists():
        shutil.rmtree(midi_dir)
    midi_dir.mkdir(parents=True, exist_ok=True)
    for pattern in ["*.mid", "*.midi"]:
        for path in export_dir.glob(pattern):
            if path.is_file():
                path.unlink()
