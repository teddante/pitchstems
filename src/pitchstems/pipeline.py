from __future__ import annotations

import contextlib
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from pitchstems.audio import normalize_to_wav
from pitchstems.midi import combine_midi_tracks
from pitchstems.project_store import PROJECT_FILENAME, load_project_manifest, save_project_manifest
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
    source_audio: Path | None = None


CancelCheck = Callable[[], bool]


class PipelineCancelledError(RuntimeError):
    """Raised when a user-requested cancellation stops pipeline orchestration."""


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
    cancelled: CancelCheck | None = None,
) -> PipelineResult:
    """Run the complete local stem-to-MIDI pipeline."""
    input_path = input_path.expanduser().resolve()
    output_root = output_root.expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    input_stem = _safe_stem(input_path.stem)
    project_dir = _project_dir(output_root, input_path)
    audio_dir = project_dir / "audio"
    work_dir = project_dir / "work"
    stems_dir = project_dir / "stems"
    midi_dir = project_dir / "midi"
    export_dir = project_dir / "export"

    for directory in [audio_dir, work_dir, stems_dir, midi_dir, export_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    try:
        project_source_audio = _copy_source_audio(input_path, audio_dir)
        _raise_if_cancelled(cancelled)
        if log:
            log(f"Preparing {input_path.name}...")
            log("Audio prep: FFmpeg -> stereo 44.1 kHz PCM WAV for native BS-RoFormer.")
            if cancelled is not None:
                log("Cancellation will take effect between native model stages.")
        normalized_audio = normalize_to_wav(project_source_audio, work_dir / f"{input_stem}.wav")
        _raise_if_cancelled(cancelled)

        stems = separate_stems(
            normalized_audio,
            stems_dir,
            profile=quality,
            options=separation_options,
            log=log,
        )
        _raise_if_cancelled(cancelled)

        midi_files: list[MidiResult] = []
        combined_midi = None
        zip_path = None
        if generate_midi and midi_policy != "none":
            midi_result = process_midi_from_stems(
                project_dir=project_dir,
                input_stem=input_stem,
                normalized_audio=normalized_audio,
                stems=stems,
                source_audio=project_source_audio,
                midi_policy=midi_policy,
                midi_options=midi_options,
                midi_stems=midi_stems,
                create_zip=False,
                log=log,
                cancelled=cancelled,
            )
            midi_files = midi_result.midi_files
            combined_midi = midi_result.combined_midi
            zip_path = project_dir / f"{input_stem}_pitchstems.zip" if create_zip else None
        else:
            if log:
                log("Skipping MIDI transcription.")
            zip_path = project_dir / f"{input_stem}_pitchstems.zip" if create_zip else None

        if log:
            log(f"Done: {zip_path or project_dir}")

        result = PipelineResult(
            project_dir=project_dir,
            normalized_audio=normalized_audio,
            stems=stems,
            midi_files=midi_files,
            combined_midi=combined_midi,
            zip_path=zip_path,
            source_audio=project_source_audio,
        )
        save_project_manifest(
            result,
            separation_options=separation_options,
            midi_options=midi_options,
            midi_stems=midi_stems,
            generate_midi=generate_midi,
            midi_policy=midi_policy,
            create_zip=create_zip,
        )
        if zip_path:
            _zip_project_outputs(project_dir, stems, midi_files, combined_midi, zip_path)
        return result
    except PipelineCancelledError:
        _remove_new_project_dir(project_dir, output_root)
        raise


def process_midi_from_stems(
    project_dir: Path,
    input_stem: str,
    normalized_audio: Path | None,
    stems: list[StemResult],
    source_audio: Path | None = None,
    midi_policy: str = "pitched",
    midi_options: MidiOptions | None = None,
    midi_stems: set[str] | None = None,
    create_zip: bool = True,
    log: Callable[[str], None] | None = None,
    cancelled: CancelCheck | None = None,
) -> PipelineResult:
    """Run or rerun Basic Pitch from already separated stems."""
    project_dir = project_dir.expanduser().resolve()
    source_audio = source_audio or _existing_source_audio(project_dir)
    midi_dir = project_dir / "midi"
    export_dir = project_dir / "export"
    staged_midi_dir = project_dir / "midi.tmp"
    staged_export_dir = project_dir / "export.tmp"
    backup_midi_dir = project_dir / "midi.backup.tmp"
    backup_export_dir = project_dir / "export.backup.tmp"
    input_stem = _safe_stem(input_stem)
    selected_midi_stems = {stem.lower() for stem in midi_stems} if midi_stems is not None else None
    if selected_midi_stems is not None and not selected_midi_stems:
        raise ValueError("Choose at least one stem before rerunning MIDI.")
    midi_dir.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)

    _reset_staging_dir(staged_midi_dir, project_dir)
    _reset_staging_dir(staged_export_dir, project_dir)
    _remove_staging_dir(backup_midi_dir, project_dir)
    _remove_staging_dir(backup_export_dir, project_dir)

    midi_files: list[MidiResult] = []
    skip_percussion = midi_policy != "all" and selected_midi_stems is None
    if log:
        log("Running Basic Pitch from existing separated stems.")

    try:
        _raise_if_cancelled(cancelled)
        for stem in stems:
            _raise_if_cancelled(cancelled)
            if selected_midi_stems is not None and stem.name.lower() not in selected_midi_stems:
                if log:
                    log(f"Skipping MIDI for {stem.name}: not selected for Basic Pitch analysis.")
                continue
            midi = transcribe_stem_to_midi(
                stem.name,
                stem.path,
                staged_midi_dir / stem.safe_key,
                skip_percussion=skip_percussion,
                options=midi_options,
                log=log,
            )
            if midi:
                midi_files.append(MidiResult(midi.stem, midi.path, stem.safe_key))
            _raise_if_cancelled(cancelled)

        staged_combined_midi = combine_midi_tracks(midi_files, staged_export_dir / f"{input_stem}_combined.mid")
        for midi in midi_files:
            shutil.copy2(midi.path, staged_export_dir / f"{midi.safe_key}.mid")

        final_midi_files = [
            MidiResult(midi.stem, midi_dir / midi.path.relative_to(staged_midi_dir), midi.safe_key)
            for midi in midi_files
        ]
        combined_midi = None
        if staged_combined_midi is not None:
            combined_midi = export_dir / staged_combined_midi.name
        staged_export_paths = list(staged_export_dir.iterdir())

        generated_export_midi = {f"{input_stem}_combined.mid"} | {
            f"{stem.safe_key}.mid"
            for stem in stems
        }
        _raise_if_cancelled(cancelled)
        _replace_midi_outputs(
            midi_dir,
            staged_midi_dir,
            export_dir,
            staged_export_paths,
            generated_export_midi,
            backup_midi_dir,
            backup_export_dir,
        )
        _remove_midi_preview_cache(project_dir)
        _remove_export_stem_copies(export_dir, stems)
        midi_files = final_midi_files
    except Exception:
        _remove_staging_dir(staged_midi_dir, project_dir)
        _remove_staging_dir(staged_export_dir, project_dir)
        _remove_staging_dir(backup_midi_dir, project_dir)
        _remove_staging_dir(backup_export_dir, project_dir)
        raise

    zip_path = project_dir / f"{input_stem}_pitchstems.zip" if create_zip else None
    if log:
        log(f"MIDI stage done: {zip_path or project_dir}")

    result = PipelineResult(
        project_dir=project_dir,
        normalized_audio=normalized_audio or project_dir / "work" / f"{input_stem}.wav",
        stems=stems,
        midi_files=midi_files,
        combined_midi=combined_midi,
        zip_path=zip_path,
        source_audio=source_audio,
    )
    save_project_manifest(
        result,
        midi_options=midi_options,
        midi_stems=midi_stems,
        generate_midi=True,
        midi_policy=midi_policy,
        create_zip=create_zip,
    )
    if zip_path:
        _zip_project_outputs(project_dir, stems, midi_files, combined_midi, zip_path)
    return result


def _project_dir(output_root: Path, input_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_name = _safe_stem(input_path.stem)
    candidate = output_root / f"{safe_name}-{timestamp}.pitchstems"
    if not candidate.exists():
        return candidate
    index = 2
    while True:
        candidate = output_root / f"{safe_name}-{timestamp}-{index}.pitchstems"
        if not candidate.exists():
            return candidate
        index += 1


def _raise_if_cancelled(cancelled: CancelCheck | None) -> None:
    if cancelled is not None and cancelled():
        raise PipelineCancelledError("Processing cancelled.")


def _copy_source_audio(input_path: Path, audio_dir: Path) -> Path:
    target = audio_dir / f"{_safe_stem(input_path.stem)}{input_path.suffix.lower()}"
    shutil.copy2(input_path, target)
    return target


def _existing_source_audio(project_dir: Path) -> Path | None:
    with contextlib.suppress(Exception):
        value = load_project_manifest(project_dir / PROJECT_FILENAME).get("source_audio")
        if isinstance(value, str) and value:
            path = Path(value)
            return path if path.is_absolute() else project_dir / path
    return None


def _safe_stem(stem: str, max_length: int = 80) -> str:
    safe = "".join(char if char.isalnum() or char in "-_" else "_" for char in stem).strip("._-")
    if not safe:
        safe = "audio"
    safe = safe[:max_length].rstrip("._-") or "audio"
    if _is_windows_reserved_name(safe):
        safe = f"audio_{safe}"
    return safe


def _is_windows_reserved_name(name: str) -> bool:
    reserved = {"CON", "PRN", "AUX", "NUL", "CLOCK$"}
    reserved.update(f"COM{index}" for index in range(1, 10))
    reserved.update(f"LPT{index}" for index in range(1, 10))
    return name.upper() in reserved


def _zip_project_outputs(
    project_dir: Path,
    stems: list[StemResult],
    midi_files: list[MidiResult],
    combined_midi: Path | None,
    zip_path: Path,
) -> Path:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for stem in stems:
            if stem.path.is_file():
                archive.write(stem.path, Path("stems") / f"{stem.safe_key}{stem.path.suffix.lower() or '.wav'}")
        for midi in midi_files:
            if midi.path.is_file():
                archive.write(midi.path, Path("midi") / f"{midi.safe_key}.mid")
        if combined_midi and combined_midi.is_file():
            archive.write(combined_midi, Path("midi") / combined_midi.name)
        manifest = project_dir / "pitchstems.project.json"
        if manifest.is_file():
            archive.write(manifest, manifest.name)
    return zip_path


def _replace_midi_outputs(
    midi_dir: Path,
    staged_midi_dir: Path,
    export_dir: Path,
    staged_export_paths: list[Path],
    generated_export_midi: set[str],
    backup_midi_dir: Path,
    backup_export_dir: Path,
) -> None:
    project_dir = midi_dir.parent
    for label, path in [
        ("MIDI output", midi_dir),
        ("staged MIDI output", staged_midi_dir),
        ("export output", export_dir),
        ("MIDI backup", backup_midi_dir),
        ("export backup", backup_export_dir),
    ]:
        _assert_project_child(project_dir, path, label)
    generated_names = {name.lower() for name in generated_export_midi}
    try:
        if midi_dir.exists():
            shutil.move(str(midi_dir), str(backup_midi_dir))
        backup_export_dir.mkdir(parents=True, exist_ok=True)
        for path in list(export_dir.iterdir()):
            if path.is_file() and path.name.lower() in generated_names:
                shutil.move(str(path), str(backup_export_dir / path.name))

        shutil.move(str(staged_midi_dir), str(midi_dir))
        for staged_path in staged_export_paths:
            _assert_project_child(project_dir, staged_path, "staged export output")
            shutil.move(str(staged_path), str(export_dir / staged_path.name))
        _remove_staging_dir(staged_midi_dir, project_dir)
        _remove_staging_dir(backup_midi_dir, project_dir)
        _remove_staging_dir(backup_export_dir, project_dir)
    except Exception:
        if midi_dir.exists():
            _remove_project_dir(midi_dir, project_dir, "partial MIDI output")
        if backup_midi_dir.exists():
            shutil.move(str(backup_midi_dir), str(midi_dir))
        if backup_export_dir.exists():
            for backup_path in backup_export_dir.iterdir():
                destination = export_dir / backup_path.name
                if destination.exists():
                    destination.unlink()
                shutil.move(str(backup_path), str(destination))
        raise


def _reset_staging_dir(path: Path, project_dir: Path | None = None) -> None:
    _remove_staging_dir(path, project_dir)
    path.mkdir(parents=True, exist_ok=True)


def _remove_staging_dir(path: Path, project_dir: Path | None = None) -> None:
    if project_dir is None:
        raise ValueError("project_dir is required for recursive staging cleanup")
    _remove_project_dir(path, project_dir, "staging directory")


def _remove_project_dir(path: Path, project_dir: Path, label: str) -> None:
    _assert_project_child(project_dir, path, label)
    if path.exists():
        if path.is_symlink():
            raise ValueError(f"{label} must not be a symlink: {path}")
        shutil.rmtree(path)


def _remove_new_project_dir(project_dir: Path, output_root: Path) -> None:
    root = output_root.expanduser().resolve()
    target = project_dir.expanduser().resolve()
    if target == root:
        raise ValueError(f"project folder must not be the output root: {target}")
    if target.suffix != ".pitchstems":
        raise ValueError(f"project folder must be a PitchStems project: {target}")
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"project folder must stay inside the output root: {target}") from exc
    if target.exists():
        if target.is_symlink():
            raise ValueError(f"project folder must not be a symlink: {target}")
        shutil.rmtree(target)


def _assert_project_child(project_dir: Path, path: Path, label: str) -> None:
    _assert_project_workspace(project_dir)
    root = project_dir.expanduser().resolve()
    target = path.expanduser().resolve()
    if target == root:
        raise ValueError(f"{label} must not be the project root: {target}")
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} must stay inside the project folder: {target}") from exc


def _assert_project_workspace(project_dir: Path) -> None:
    root = project_dir.expanduser().resolve()
    if root.anchor == str(root):
        raise ValueError(f"project folder must not be a filesystem root: {root}")
    if root.suffix != ".pitchstems" and not (root / PROJECT_FILENAME).exists():
        raise ValueError(f"project folder must be a PitchStems project: {root}")


def _remove_export_stem_copies(export_dir: Path, stems: list[StemResult]) -> None:
    for stem in stems:
        duplicate = export_dir / stem.path.name
        if _looks_like_copied_file(stem.path, duplicate):
            duplicate.unlink()


def _remove_midi_preview_cache(project_dir: Path) -> None:
    with contextlib.suppress(OSError):
        _remove_staging_dir(project_dir / "editor" / "midi-preview", project_dir)


def _looks_like_copied_file(source: Path, candidate: Path) -> bool:
    if not source.is_file() or not candidate.is_file():
        return False
    try:
        source_stat = source.stat()
        candidate_stat = candidate.stat()
    except OSError:
        return False
    return (
        source_stat.st_size == candidate_stat.st_size
        and source_stat.st_mtime_ns == candidate_stat.st_mtime_ns
    )
