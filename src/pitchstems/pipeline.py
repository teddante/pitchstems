from __future__ import annotations

import contextlib
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from collections.abc import Callable

from pitchstems.atomic_files import atomic_replace
from pitchstems.audio import normalize_to_wav
from pitchstems.audio_clip import AudioClipRange
from pitchstems.export_files import combined_midi_archive_path, midi_archive_path, stem_archive_path
from pitchstems.input_validation import validate_audio_input
from pitchstems.midi import combine_midi_tracks
from pitchstems.pipeline_models import MidiResult, PipelineResult, StemResult
from pitchstems.runtime_checks import run_preflight
from pitchstems.project_lock import project_mutation_lock, try_project_mutation_lock
from pitchstems.project_store import (
    PROJECT_FILENAME,
    load_pipeline_result,
    save_failed_project_manifest,
    save_project_manifest,
)
from pitchstems.separation import SeparationOptions, separate_stems
from pitchstems.transcription import MidiOptions, transcribe_stem_to_midi
from pitchstems.midi_transaction import (
    _MidiWorkspace,
    _ProjectPaths,
    _assert_project_child,
    _commit_midi_transaction,
    _recover_midi_transaction,
    _remove_staging_dir,
    _replace_midi_outputs,
    _safe_stem,
)


@dataclass(frozen=True)
class _ProjectWorkspace(_ProjectPaths):
    project_dir: Path
    input_stem: str
    audio_dir: Path
    work_dir: Path
    stems_dir: Path
    midi_dir: Path
    export_dir: Path

    @classmethod
    def from_input(cls, output_root: Path, input_path: Path) -> _ProjectWorkspace:
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

    def create_directories(self) -> None:
        for directory in [
            self.audio_dir,
            self.work_dir,
            self.stems_dir,
            self.midi_dir,
            self.export_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)


def process_audio_file(
    input_path: Path,
    output_root: Path,
    separation_options: SeparationOptions | None = None,
    generate_midi: bool = True,
    midi_policy: str = "pitched",
    midi_options: MidiOptions | None = None,
    midi_stems: set[str] | None = None,
    create_zip: bool = True,
    log: Callable[[str], None] | None = None,
    project_created: Callable[[Path], None] | None = None,
    source_clip: AudioClipRange | None = None,
    generate_chord_suggestions: bool = True,
) -> PipelineResult:
    """Run the complete local stem-to-MIDI pipeline."""
    input_path = input_path.expanduser().resolve()
    output_root = output_root.expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(input_path)
    input_error = validate_audio_input(input_path)
    if input_error:
        raise ValueError(input_error)

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
        if log:
            log(f"Preparing {input_path.name}...")
            log("Audio prep: FFmpeg -> stereo 44.1 kHz PCM WAV for native BS-RoFormer.")
            if source_clip is not None:
                log(
                    "Import clip: "
                    f"{source_clip.start_seconds:.2f}s - {source_clip.end_seconds:.2f}s "
                    f"({source_clip.duration_seconds:.2f}s)."
                )
        normalized_audio = normalize_to_wav(normalize_input, normalized_audio, clip_range=source_clip)
        if source_clip is not None:
            try:
                project_source_audio.hardlink_to(normalized_audio)
            except OSError:
                shutil.copy2(normalized_audio, project_source_audio)

        stems = separate_stems(
            normalized_audio,
            workspace.stems_dir,
            options=separation_options,
            log=log,
        )

        midi_files: list[MidiResult] = []
        combined_midi = None
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
            )
            midi_files = midi_result.midi_files
            combined_midi = midi_result.combined_midi
            # The MIDI stage saved a complete manifest; a later packaging error
            # must not overwrite it with a "failed" one.
            project_manifest_written = True
        elif log:
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
        save_project_manifest(
            result,
            separation_options=separation_options,
            midi_options=midi_options,
            midi_stems=midi_stems,
            generate_midi=generate_midi,
            midi_policy=midi_policy,
            create_zip=create_zip,
            generate_chord_suggestions=generate_chord_suggestions,
        )
        project_manifest_written = True
        _package_pipeline_outputs(result)
        if log:
            log(f"Done: {zip_path or workspace.project_dir}")
        return result
    except KeyboardInterrupt:
        remove_new_project_dir(workspace.project_dir, output_root)
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

    if log:
        log("Running Basic Pitch from existing separated stems.")

    try:
        staged_midi_files = _transcribe_selected_stems(
            workspace,
            stems,
            midi_policy=midi_policy,
            selected_midi_stems=selected_midi_stems,
            midi_options=midi_options,
            log=log,
        )
        midi_files, combined_midi = _publish_staged_midi(workspace, stems, staged_midi_files)
    except BaseException:
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
        save_project_manifest(
            result,
            midi_options=midi_options,
            midi_stems=midi_stems,
            generate_midi=True,
            midi_policy=midi_policy,
            create_zip=create_zip,
        )
        _commit_midi_transaction(workspace)
    except BaseException:
        _recover_midi_transaction(workspace)
        raise
    _package_pipeline_outputs(result)
    return result


def _transcribe_selected_stems(
    workspace: _MidiWorkspace,
    stems: list[StemResult],
    *,
    midi_policy: str,
    selected_midi_stems: set[str] | None,
    midi_options: MidiOptions | None,
    log: Callable[[str], None] | None,
) -> list[MidiResult]:
    """Write Basic Pitch MIDI for the selected stems into the staging folder."""
    skip_percussion = midi_policy != "all" and selected_midi_stems is None
    midi_files: list[MidiResult] = []
    for stem in stems:
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
    return midi_files


def _publish_staged_midi(
    workspace: _MidiWorkspace,
    stems: list[StemResult],
    staged_midi_files: list[MidiResult],
) -> tuple[list[MidiResult], Path | None]:
    """Replace the project's MIDI and export files with the staged ones.

    Returns the final per-stem MIDI results and the combined MIDI path, if one was written.
    """
    staged_combined_midi = combine_midi_tracks(
        staged_midi_files,
        workspace.staged_export_dir / f"{workspace.input_stem}_combined.mid",
    )
    for midi in staged_midi_files:
        shutil.copy2(midi.path, workspace.staged_export_dir / f"{midi.safe_key}.mid")

    final_midi_files = [
        MidiResult(
            midi.stem,
            workspace.midi_dir / midi.path.relative_to(workspace.staged_midi_dir),
            midi.safe_key,
        )
        for midi in staged_midi_files
    ]
    combined_midi = None
    if staged_combined_midi is not None:
        combined_midi = workspace.export_dir / staged_combined_midi.name
    staged_export_paths = list(workspace.staged_export_dir.iterdir())

    generated_export_midi = {f"{workspace.input_stem}_combined.mid"} | {
        f"{stem.safe_key}.mid"
        for stem in stems
    }
    _replace_midi_outputs(
        workspace,
        staged_export_paths,
        generated_export_midi,
    )
    return final_midi_files, combined_midi


def recover_interrupted_midi_update(project_dir: Path) -> bool:
    """Roll back a MIDI rerun that was killed mid-swap, if one is pending.

    Returns True when recovery ran. Skips (returns False) when nothing is pending
    or another process currently holds the project mutation lock.
    """
    project_dir = project_dir.expanduser().resolve()
    workspace = _MidiWorkspace.from_project(project_dir, project_dir.stem)
    if not workspace.has_interrupted_update():
        return False
    with try_project_mutation_lock(project_dir) as acquired:
        if not acquired or not workspace.has_interrupted_update():
            return False
        _recover_midi_transaction(workspace)
        return True


def _package_pipeline_outputs(result: PipelineResult) -> Path | None:
    if result.zip_path is None:
        return None
    return _zip_project_outputs(
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


def _zip_project_outputs(
    stems: list[StemResult],
    midi_files: list[MidiResult],
    combined_midi: Path | None,
    zip_path: Path,
) -> Path:
    with atomic_replace(zip_path) as temporary, zipfile.ZipFile(
        temporary, "w", zipfile.ZIP_DEFLATED
    ) as archive:
        for stem in stems:
            if stem.path.is_file():
                archive.write(stem.path, _safe_archive_path(stem_archive_path(stem)))
        for midi in midi_files:
            if midi.path.is_file():
                archive.write(midi.path, _safe_archive_path(midi_archive_path(midi)))
        if combined_midi and combined_midi.is_file():
            archive.write(combined_midi, _safe_archive_path(combined_midi_archive_path(combined_midi)))
    return zip_path


def _safe_archive_path(path: Path) -> str:
    if path.is_absolute() or path.anchor or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"Archive path must be a safe relative path: {path}")
    return path.as_posix()


def _reset_staging_dir(path: Path, project_dir: Path) -> None:
    _remove_staging_dir(path, project_dir)
    path.mkdir(parents=True, exist_ok=True)


def remove_new_project_dir(project_dir: Path, output_root: Path) -> None:
    """Delete a partially created project folder, refusing anything that is not one."""
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
