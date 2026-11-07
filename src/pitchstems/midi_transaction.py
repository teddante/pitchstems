from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from pitchstems.atomic_files import atomic_replace, write_json_atomic
from pitchstems.filename_safety import safe_file_stem
from pitchstems.project_store import (
    PROJECT_FILENAME,
    restore_project_manifest_backup,
)


class _MidiTransaction(TypedDict):
    phase: str
    generated_export_midi: list[str]
    had_midi_dir: bool


class _ProjectPaths:
    project_dir: Path
    input_stem: str

    @property
    def normalized_audio(self) -> Path:
        return self.project_dir / "work" / f"{self.input_stem}.wav"

    @property
    def zip_path(self) -> Path:
        return self.project_dir / f"{self.input_stem}_pitchstems.zip"


@dataclass(frozen=True)
class _MidiWorkspace(_ProjectPaths):
    project_dir: Path
    input_stem: str
    midi_dir: Path
    export_dir: Path
    staged_midi_dir: Path
    staged_export_dir: Path
    backup_midi_dir: Path
    backup_export_dir: Path
    transaction_path: Path
    manifest_backup_path: Path

    @classmethod
    def from_project(cls, project_dir: Path, input_stem: str) -> _MidiWorkspace:
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
            manifest_backup_path=project_dir / ".midi-transaction.manifest.json",
        )

    def has_interrupted_update(self) -> bool:
        return any(
            path.exists()
            for path in (
                self.transaction_path,
                self.backup_midi_dir,
                self.backup_export_dir,
                self.manifest_backup_path,
            )
        )


def _safe_stem(stem: str, max_length: int = 80) -> str:
    return safe_file_stem(stem, fallback="audio", max_length=max_length)


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
        ("manifest backup", workspace.manifest_backup_path),
    ]:
        _assert_project_child(project_dir, path, label)
    generated_names = {name.lower() for name in generated_export_midi}
    had_midi_dir = workspace.midi_dir.exists()
    manifest_path = project_dir / PROJECT_FILENAME
    workspace.manifest_backup_path.unlink(missing_ok=True)
    if manifest_path.is_file():
        with atomic_replace(workspace.manifest_backup_path) as temporary:
            shutil.copy2(manifest_path, temporary)
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
    write_json_atomic(workspace.transaction_path, payload, fsync=True)


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
        if workspace.manifest_backup_path.is_file():
            restore_project_manifest_backup(workspace.project_dir, workspace.manifest_backup_path)
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
    workspace.manifest_backup_path.unlink(missing_ok=True)
    workspace.transaction_path.unlink(missing_ok=True)


def _remove_staging_dir(path: Path, project_dir: Path) -> None:
    _remove_project_dir(path, project_dir, "staging directory")


def _remove_project_dir(path: Path, project_dir: Path, label: str) -> None:
    _assert_project_child(project_dir, path, label)
    if path.exists():
        if path.is_symlink():
            raise ValueError(f"{label} must not be a symlink: {path}")
        shutil.rmtree(path)


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
