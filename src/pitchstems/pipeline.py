from __future__ import annotations

import contextlib
import json
import os
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, TypedDict

from pitchstems.audio import normalize_to_wav
from pitchstems.audio_clip import AudioClipRange
from pitchstems.filename_safety import safe_file_stem
from pitchstems.midi import combine_midi_tracks
from pitchstems.pipeline_models import MidiResult, PipelineResult, StemResult
from pitchstems.preflight import run_preflight
from pitchstems.project_lock import project_mutation_lock
from pitchstems.project_store import (
    PROJECT_FILENAME,
    load_pipeline_result,
    save_failed_project_manifest,
    save_project_manifest,
)
from pitchstems.separation import SeparationOptions, separate_stems
from pitchstems.transcription import MidiOptions, transcribe_stem_to_midi


CancelCheck = Callable[[], bool]


class PipelineCancelledError(RuntimeError):
    """Raised when a user-requested cancellation stops pipeline orchestration."""


class _MidiTransaction(TypedDict):
    phase: str
    generated_export_midi: list[str]
    had_midi_dir: bool


@dataclass(frozen=True)
class _ProjectWorkspace:
    project_dir: Path
    input_stem: str
    audio_dir: Path
    work_dir: Path
    stems_dir: Path
    midi_dir: Path
    export_dir: Path

    @classmethod
    def from_input(cls, output_root: Path, input_path: Path) -> "_ProjectWorkspace":
        project_dir = _reserve_project_dir(output_root, input_path)
        input_stem = _safe_stem(input_path.stem)
        return cls(
            project_dir=project_dir,
            input_stem=input_stem,
            audio_dir=project_dir / "audio",
            work_dir=project_dir / "work",
            stems_dir=project_dir / "stems",
            midi_dir=project_dir / "midi",
            export_dir=project_dir / "export",
        )

    @property
    def normalized_audio(self) -> Path:
        return self.work_dir / f"{self.input_stem}.wav"

    @property
    def zip_path(self) -> Path:
        return self.project_dir / f"{self.input_stem}_pitchstems.zip"

    def create_directories(self) -> None:
        for directory in [
            self.audio_dir,
            self.work_dir,
            self.stems_dir,
            self.midi_dir,
            self.export_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class _MidiWorkspace:
    project_dir: Path
    input_stem: str
    midi_dir: Path
    export_dir: Path
    staged_midi_dir: Path
    staged_export_dir: Path
    backup_midi_dir: Path
    backup_export_dir: Path
    transaction_path: Path

    @classmethod
    def from_project(cls, project_dir: Path, input_stem: str) -> "_MidiWorkspace":
        input_stem = _safe_stem(input_stem)
        return cls(
            project_dir=project_dir,
            input_stem=input_stem,
            midi_dir=project_dir / "midi",
            export_dir=project_dir / "export",
            staged_midi_dir=project_dir / "midi.tmp",
            staged_export_dir=project_dir / "export.tmp",
            backup_midi_dir=project_dir / "midi.backup.tmp",
            backup_export_dir=project_dir / "export.backup.tmp",
            transaction_path=project_dir / ".midi-transaction.json",
        )

    @property
    def normalized_audio(self) -> Path:
        return self.project_dir / "work" / f"{self.input_stem}.wav"

    @property
    def zip_path(self) -> Path:
        return self.project_dir / f"{self.input_stem}_pitchstems.zip"


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
    project_created: Callable[[Path], None] | None = None,
    source_clip: AudioClipRange | None = None,
) -> PipelineResult:
    """Run the complete local stem-to-MIDI pipeline."""
    input_path = input_path.expanduser().resolve()
    output_root = output_root.expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    report = run_preflight(
        require_ml=True,
        require_transcription=generate_midi and midi_policy != "none",
        requested_device=separation_options.device if separation_options else None,
        output_root=output_root,
        model_key=separation_options.model_key if separation_options else None,
    )
    if not report.ok:
        raise RuntimeError(f"Preflight failed: {report.failure_summary()}")

    workspace = _ProjectWorkspace.from_input(output_root, input_path)
    workspace.create_directories()
    if project_created is not None:
        project_created(workspace.project_dir)

    project_source_audio: Path | None = None
    normalized_audio = workspace.normalized_audio
    project_manifest_written = False
    try:
        project_source_audio, normalize_input = _prepare_source_audio_input(
            input_path,
            workspace,
            source_clip,
        )
        _raise_if_cancelled(cancelled)
        if log:
            log(f"Preparing {input_path.name}...")
            log("Audio prep: FFmpeg -> stereo 44.1 kHz PCM WAV for native BS-RoFormer.")
            if source_clip is not None:
                log(
                    "Import clip: "
                    f"{source_clip.start_seconds:.2f}s - {source_clip.end_seconds:.2f}s "
                    f"({source_clip.duration_seconds:.2f}s)."
                )
            if cancelled is not None:
                log("Cancellation will take effect between native model stages.")
        normalized_audio = normalize_to_wav(normalize_input, normalized_audio, clip_range=source_clip)
        if source_clip is not None:
            try:
                project_source_audio.hardlink_to(normalized_audio)
            except OSError:
                shutil.copy2(normalized_audio, project_source_audio)
        _raise_if_cancelled(cancelled)

        stems = separate_stems(
            normalized_audio,
            workspace.stems_dir,
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
                project_dir=workspace.project_dir,
                input_stem=workspace.input_stem,
                normalized_audio=normalized_audio,
                stems=stems,
                source_audio=project_source_audio,
                source_clip=source_clip,
                midi_policy=midi_policy,
                midi_options=midi_options,
                midi_stems=midi_stems,
                create_zip=False,
                log=log,
                cancelled=cancelled,
            )
            midi_files = midi_result.midi_files
            combined_midi = midi_result.combined_midi
            zip_path = workspace.zip_path if create_zip else None
        else:
            if log:
                log("Skipping MIDI transcription.")
            zip_path = workspace.zip_path if create_zip else None

        result = PipelineResult(
            project_dir=workspace.project_dir,
            normalized_audio=normalized_audio,
            stems=stems,
            midi_files=midi_files,
            combined_midi=combined_midi,
            zip_path=zip_path,
            source_audio=project_source_audio,
            source_clip=source_clip,
        )
        _save_pipeline_manifest(
            result,
            separation_options=separation_options,
            midi_options=midi_options,
            midi_stems=midi_stems,
            generate_midi=generate_midi,
            midi_policy=midi_policy,
            create_zip=create_zip,
        )
        project_manifest_written = True
        _package_pipeline_outputs(result)
        if log:
            log(f"Done: {zip_path or workspace.project_dir}")
        return result
    except PipelineCancelledError:
        _remove_new_project_dir(workspace.project_dir, output_root)
        raise
    except Exception as exc:
        if not project_manifest_written:
            save_failed_project_manifest(
                workspace.project_dir,
                project_source_audio,
                normalized_audio,
                str(exc),
            )
        raise


def process_midi_from_stems(
    project_dir: Path,
    input_stem: str,
    normalized_audio: Path | None,
    stems: list[StemResult],
    source_audio: Path | None = None,
    source_clip: AudioClipRange | None = None,
    midi_policy: str = "pitched",
    midi_options: MidiOptions | None = None,
    midi_stems: set[str] | None = None,
    create_zip: bool = True,
    log: Callable[[str], None] | None = None,
    cancelled: CancelCheck | None = None,
) -> PipelineResult:
    """Run or rerun Basic Pitch from already separated stems."""
    project_dir = project_dir.expanduser().resolve()
    with project_mutation_lock(project_dir):
        return _process_midi_from_stems_unlocked(
            project_dir=project_dir,
            input_stem=input_stem,
            normalized_audio=normalized_audio,
            stems=stems,
            source_audio=source_audio,
            source_clip=source_clip,
            midi_policy=midi_policy,
            midi_options=midi_options,
            midi_stems=midi_stems,
            create_zip=create_zip,
            log=log,
            cancelled=cancelled,
        )


def _process_midi_from_stems_unlocked(
    project_dir: Path,
    input_stem: str,
    normalized_audio: Path | None,
    stems: list[StemResult],
    source_audio: Path | None = None,
    source_clip: AudioClipRange | None = None,
    midi_policy: str = "pitched",
    midi_options: MidiOptions | None = None,
    midi_stems: set[str] | None = None,
    create_zip: bool = True,
    log: Callable[[str], None] | None = None,
    cancelled: CancelCheck | None = None,
) -> PipelineResult:
    existing_source_audio, existing_source_clip = _existing_source_metadata(project_dir)
    source_audio = source_audio or existing_source_audio
    source_clip = source_clip or existing_source_clip
    workspace = _MidiWorkspace.from_project(project_dir, input_stem)
    selected_midi_stems = _selected_midi_stem_keys(midi_stems)
    workspace.midi_dir.mkdir(parents=True, exist_ok=True)
    workspace.export_dir.mkdir(parents=True, exist_ok=True)

    _recover_midi_transaction(workspace)
    _reset_staging_dir(workspace.staged_midi_dir, workspace.project_dir)
    _reset_staging_dir(workspace.staged_export_dir, workspace.project_dir)

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
            stem_output_dir = workspace.staged_midi_dir / stem.safe_key
            _assert_project_child(workspace.project_dir, stem_output_dir, "stem MIDI output")
            midi = transcribe_stem_to_midi(
                stem.name,
                stem.path,
                stem_output_dir,
                skip_percussion=skip_percussion,
                options=midi_options,
                log=log,
            )
            if midi:
                midi_files.append(MidiResult(midi.stem, midi.path, stem.safe_key))
            _raise_if_cancelled(cancelled)

        staged_combined_midi = combine_midi_tracks(
            midi_files,
            workspace.staged_export_dir / f"{workspace.input_stem}_combined.mid",
        )
        for midi in midi_files:
            shutil.copy2(midi.path, workspace.staged_export_dir / f"{midi.safe_key}.mid")

        final_midi_files = [
            MidiResult(
                midi.stem,
                workspace.midi_dir / midi.path.relative_to(workspace.staged_midi_dir),
                midi.safe_key,
            )
            for midi in midi_files
        ]
        combined_midi = None
        if staged_combined_midi is not None:
            combined_midi = workspace.export_dir / staged_combined_midi.name
        staged_export_paths = list(workspace.staged_export_dir.iterdir())

        generated_export_midi = {f"{workspace.input_stem}_combined.mid"} | {
            f"{stem.safe_key}.mid"
            for stem in stems
        }
        _raise_if_cancelled(cancelled)
        _replace_midi_outputs(
            workspace,
            staged_export_paths,
            generated_export_midi,
        )
        _remove_midi_preview_cache(workspace.project_dir)
        _remove_export_stem_copies(workspace.export_dir, stems)
        midi_files = final_midi_files
    except Exception:
        _recover_midi_transaction(workspace)
        raise

    zip_path = workspace.zip_path if create_zip else None
    if log:
        log(f"MIDI stage done: {zip_path or workspace.project_dir}")

    result = PipelineResult(
        project_dir=workspace.project_dir,
        normalized_audio=normalized_audio or workspace.normalized_audio,
        stems=stems,
        midi_files=midi_files,
        combined_midi=combined_midi,
        zip_path=zip_path,
        source_audio=source_audio,
        source_clip=source_clip,
    )
    try:
        _save_pipeline_manifest(
            result,
            midi_options=midi_options,
            midi_stems=midi_stems,
            generate_midi=True,
            midi_policy=midi_policy,
            create_zip=create_zip,
        )
        _commit_midi_transaction(workspace)
        _package_pipeline_outputs(result)
    except Exception:
        _recover_midi_transaction(workspace)
        raise
    return result


def _save_pipeline_manifest(
    result: PipelineResult,
    *,
    separation_options: SeparationOptions | None = None,
    midi_options: MidiOptions | None = None,
    midi_stems: set[str] | None = None,
    generate_midi: bool,
    midi_policy: str,
    create_zip: bool,
) -> None:
    save_project_manifest(
        result,
        separation_options=separation_options,
        midi_options=midi_options,
        midi_stems=midi_stems,
        generate_midi=generate_midi,
        midi_policy=midi_policy,
        create_zip=create_zip,
    )


def _package_pipeline_outputs(result: PipelineResult) -> Path | None:
    if result.zip_path is None:
        return None
    return _zip_project_outputs(
        result.project_dir,
        result.stems,
        result.midi_files,
        result.combined_midi,
        result.zip_path,
    )


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


def _reserve_project_dir(output_root: Path, input_path: Path) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    while True:
        candidate = _project_dir(output_root, input_path)
        try:
            candidate.mkdir(exist_ok=False)
        except FileExistsError:
            continue
        return candidate


def _raise_if_cancelled(cancelled: CancelCheck | None) -> None:
    if cancelled is not None and cancelled():
        raise PipelineCancelledError("Processing cancelled.")


def _selected_midi_stem_keys(midi_stems: set[str] | None) -> set[str] | None:
    if midi_stems is None:
        return None
    selected_midi_stems = {stem.lower() for stem in midi_stems}
    if not selected_midi_stems:
        raise ValueError("Choose at least one stem before rerunning MIDI.")
    return selected_midi_stems


def _copy_source_audio(input_path: Path, audio_dir: Path) -> Path:
    target = audio_dir / f"{_safe_stem(input_path.stem)}{input_path.suffix.lower()}"
    shutil.copy2(input_path, target)
    return target


def _prepare_source_audio_input(
    input_path: Path,
    workspace: _ProjectWorkspace,
    source_clip: AudioClipRange | None,
) -> tuple[Path, Path]:
    if source_clip is None:
        project_source_audio = _copy_source_audio(input_path, workspace.audio_dir)
        return project_source_audio, project_source_audio
    project_source_audio = workspace.audio_dir / f"{workspace.input_stem}_clip.wav"
    return project_source_audio, input_path


def _existing_source_metadata(project_dir: Path) -> tuple[Path | None, AudioClipRange | None]:
    with contextlib.suppress(Exception):
        result = load_pipeline_result(project_dir / PROJECT_FILENAME)
        return result.source_audio, result.source_clip
    return None, None


def _safe_stem(stem: str, max_length: int = 80) -> str:
    return safe_file_stem(stem, fallback="audio", max_length=max_length)


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
                archive.write(
                    stem.path,
                    _safe_archive_path(
                        Path("stems") / f"{stem.safe_key}{stem.path.suffix.lower() or '.wav'}"
                    ),
                )
        for midi in midi_files:
            if midi.path.is_file():
                archive.write(midi.path, _safe_archive_path(Path("midi") / f"{midi.safe_key}.mid"))
        if combined_midi and combined_midi.is_file():
            archive.write(combined_midi, Path("midi") / combined_midi.name)
    return zip_path


def _safe_archive_path(path: Path) -> str:
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"Archive path must be a safe relative path: {path}")
    return path.as_posix()


def _replace_midi_outputs(
    workspace: _MidiWorkspace,
    staged_export_paths: list[Path],
    generated_export_midi: set[str],
) -> None:
    project_dir = workspace.project_dir
    for label, path in [
        ("MIDI output", workspace.midi_dir),
        ("staged MIDI output", workspace.staged_midi_dir),
        ("export output", workspace.export_dir),
        ("MIDI backup", workspace.backup_midi_dir),
        ("export backup", workspace.backup_export_dir),
        ("MIDI transaction", workspace.transaction_path),
    ]:
        _assert_project_child(project_dir, path, label)
    generated_names = {name.lower() for name in generated_export_midi}
    had_midi_dir = workspace.midi_dir.exists()
    _write_midi_transaction(workspace, "prepared", generated_names, had_midi_dir)
    try:
        if workspace.midi_dir.exists():
            shutil.move(str(workspace.midi_dir), str(workspace.backup_midi_dir))
        workspace.backup_export_dir.mkdir(parents=True, exist_ok=True)
        for path in list(workspace.export_dir.iterdir()):
            if path.is_file() and path.name.lower() in generated_names:
                shutil.move(str(path), str(workspace.backup_export_dir / path.name))

        _write_midi_transaction(workspace, "backed_up", generated_names, had_midi_dir)
        shutil.move(str(workspace.staged_midi_dir), str(workspace.midi_dir))
        for staged_path in staged_export_paths:
            _assert_project_child(project_dir, staged_path, "staged export output")
            shutil.move(str(staged_path), str(workspace.export_dir / staged_path.name))
        _write_midi_transaction(workspace, "installed", generated_names, had_midi_dir)
    except Exception:
        _recover_midi_transaction(workspace)
        raise


def _write_midi_transaction(
    workspace: _MidiWorkspace,
    phase: str,
    generated_export_midi: set[str],
    had_midi_dir: bool,
) -> None:
    payload = {
        "phase": phase,
        "generated_export_midi": sorted(generated_export_midi),
        "had_midi_dir": had_midi_dir,
    }
    temporary = workspace.transaction_path.with_name(
        f".{workspace.transaction_path.name}.{os.getpid()}.tmp"
    )
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(workspace.transaction_path)


def _commit_midi_transaction(workspace: _MidiWorkspace) -> None:
    if not workspace.transaction_path.exists():
        return
    transaction = _read_midi_transaction(workspace)
    _write_midi_transaction(
        workspace,
        "committed",
        set(transaction["generated_export_midi"]),
        transaction["had_midi_dir"],
    )
    _cleanup_midi_transaction(workspace)


def _recover_midi_transaction(workspace: _MidiWorkspace) -> None:
    transaction = _read_midi_transaction(workspace) if workspace.transaction_path.exists() else None
    if transaction is not None and transaction["phase"] == "committed":
        _cleanup_midi_transaction(workspace)
        return

    phase = transaction["phase"] if transaction is not None else "legacy"
    generated_names = set(transaction["generated_export_midi"]) if transaction is not None else set()
    had_midi_dir = transaction["had_midi_dir"] if transaction is not None else None

    if phase in {"backed_up", "installed"}:
        if had_midi_dir and not workspace.backup_midi_dir.exists():
            raise RuntimeError("Cannot recover interrupted MIDI update: the MIDI backup is missing.")
        if workspace.midi_dir.exists():
            _remove_project_dir(workspace.midi_dir, workspace.project_dir, "partial MIDI output")
        if workspace.backup_midi_dir.exists():
            shutil.move(str(workspace.backup_midi_dir), str(workspace.midi_dir))
        for name in generated_names:
            destination = workspace.export_dir / name
            _assert_project_child(workspace.project_dir, destination, "generated MIDI export")
            if destination.is_file() or destination.is_symlink():
                destination.unlink()
    elif workspace.backup_midi_dir.exists():
        if workspace.midi_dir.exists():
            _remove_project_dir(workspace.midi_dir, workspace.project_dir, "partial MIDI output")
        shutil.move(str(workspace.backup_midi_dir), str(workspace.midi_dir))

    if workspace.backup_export_dir.exists():
        if workspace.backup_export_dir.is_symlink():
            raise ValueError(f"MIDI export backup must not be a symlink: {workspace.backup_export_dir}")
        workspace.export_dir.mkdir(parents=True, exist_ok=True)
        for backup_path in workspace.backup_export_dir.iterdir():
            destination = workspace.export_dir / backup_path.name
            _assert_project_child(workspace.project_dir, destination, "restored MIDI export")
            if destination.exists() or destination.is_symlink():
                if destination.is_dir() and not destination.is_symlink():
                    _remove_project_dir(destination, workspace.project_dir, "partial MIDI export")
                else:
                    destination.unlink()
            shutil.move(str(backup_path), str(destination))

    _cleanup_midi_transaction(workspace)


def _read_midi_transaction(workspace: _MidiWorkspace) -> _MidiTransaction:
    try:
        payload = json.loads(workspace.transaction_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot read interrupted MIDI transaction: {workspace.transaction_path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Invalid MIDI transaction marker: {workspace.transaction_path}")
    phase = payload.get("phase")
    generated = payload.get("generated_export_midi")
    had_midi_dir = payload.get("had_midi_dir")
    if (
        phase not in {"prepared", "backed_up", "installed", "committed"}
        or not isinstance(generated, list)
        or not all(isinstance(name, str) and Path(name).name == name for name in generated)
        or not isinstance(had_midi_dir, bool)
    ):
        raise RuntimeError(f"Invalid MIDI transaction marker: {workspace.transaction_path}")
    return {
        "phase": phase,
        "generated_export_midi": generated,
        "had_midi_dir": had_midi_dir,
    }


def _cleanup_midi_transaction(workspace: _MidiWorkspace) -> None:
    for path in (
        workspace.staged_midi_dir,
        workspace.staged_export_dir,
        workspace.backup_midi_dir,
        workspace.backup_export_dir,
    ):
        _remove_staging_dir(path, workspace.project_dir)
    workspace.transaction_path.unlink(missing_ok=True)


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
