from __future__ import annotations

import os
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from pitchstems.filename_safety import safe_file_stem
from pitchstems.pipeline_models import PipelineResult


@dataclass(frozen=True)
class ExportItem:
    label: str
    category: str
    source_path: Path
    relative_path: Path
    default_selected: bool = True


@dataclass(frozen=True)
class ExportSummary:
    destination: Path
    file_count: int
    relative_paths: tuple[Path, ...]


class ExportCancelledError(RuntimeError):
    """Raised when a selected-files export is cancelled."""


def build_export_items(result: PipelineResult) -> list[ExportItem]:
    items: list[ExportItem] = []
    seen: set[Path] = set()

    if result.source_audio and result.source_audio.is_file():
        _append_item(
            items,
            seen,
            "Source audio",
            "Source Audio",
            result.source_audio,
            Path("audio") / _safe_filename(result.source_audio.name),
            default_selected=False,
        )

    for stem in result.stems:
        if stem.path.is_file():
            relative_path = Path("stems") / f"{stem.safe_key}{stem.path.suffix.lower() or '.wav'}"
            _append_item(items, seen, stem.name, "Stems", stem.path, relative_path)

    for midi in result.midi_files:
        if midi.path.is_file():
            _append_item(items, seen, midi.stem, "MIDI", midi.path, Path("midi") / f"{midi.safe_key}.mid")
            note_csvs = sorted(path for path in midi.path.parent.glob("*.csv") if path.is_file())
            for relative_path, csv_path in _note_csv_paths(midi.safe_key, note_csvs):
                _append_item(items, seen, f"{midi.stem} notes", "Notes CSV", csv_path, relative_path)

    if result.combined_midi and result.combined_midi.is_file():
        _append_item(
            items,
            seen,
            "Combined MIDI",
            "Combined MIDI",
            result.combined_midi,
            Path("midi") / _safe_filename(result.combined_midi.name),
        )

    return items


def export_collisions(items: list[ExportItem], destination: Path) -> tuple[Path, ...]:
    destination = destination.expanduser().resolve()
    return tuple(
        target
        for item in items
        if (target := _contained_export_target(destination, item.relative_path)).exists()
    )


def copy_export_items(
    items: list[ExportItem],
    destination: Path,
    *,
    overwrite: bool = False,
    cancelled: Callable[[], bool] | None = None,
    progress: Callable[[int, int, Path], None] | None = None,
) -> ExportSummary:
    if not items:
        raise ValueError("Choose at least one file to export.")

    destination = destination.expanduser().resolve()
    relative_paths: list[Path] = []
    seen_targets: set[str] = set()
    targets: list[tuple[ExportItem, Path]] = []
    for item in items:
        target = _contained_export_target(destination, item.relative_path)
        target_key = str(target).casefold()
        if target_key in seen_targets:
            raise ValueError(f"Multiple export items target the same file: {item.relative_path}")
        seen_targets.add(target_key)
        if target.exists() and not overwrite:
            raise FileExistsError(f"Export destination already exists: {target}")
        targets.append((item, target))

    total_bytes = sum(item.source_path.stat().st_size for item, _target in targets)
    copied_bytes = 0
    for item, target in targets:
        if cancelled is not None and cancelled():
            raise ExportCancelledError("Export cancelled.")
        target.parent.mkdir(parents=True, exist_ok=True)
        _contained_export_target(destination, item.relative_path)
        copied_bytes = _copy_file_atomic(
            item.source_path,
            target,
            overwrite=overwrite,
            cancelled=cancelled,
            copied_bytes=copied_bytes,
            total_bytes=total_bytes,
            progress=progress,
        )
        relative_paths.append(item.relative_path)
    return ExportSummary(
        destination=destination,
        file_count=len(items),
        relative_paths=tuple(relative_paths),
    )


def _contained_export_target(destination: Path, relative_path: Path) -> Path:
    if relative_path.is_absolute():
        raise ValueError(f"Export path must be relative: {relative_path}")
    target = (destination / relative_path).resolve()
    try:
        target.relative_to(destination)
    except ValueError as exc:
        raise ValueError(f"Export path must stay inside the destination: {relative_path}") from exc
    if target == destination:
        raise ValueError(f"Export path must name a file: {relative_path}")
    return target


def _copy_file_atomic(
    source: Path,
    target: Path,
    *,
    overwrite: bool,
    cancelled: Callable[[], bool] | None,
    copied_bytes: int,
    total_bytes: int,
    progress: Callable[[int, int, Path], None] | None,
) -> int:
    temporary = target.with_name(f".{target.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with source.open("rb") as source_handle, temporary.open("xb") as target_handle:
            while chunk := source_handle.read(1024 * 1024):
                if cancelled is not None and cancelled():
                    raise ExportCancelledError("Export cancelled.")
                target_handle.write(chunk)
                copied_bytes += len(chunk)
                if progress is not None:
                    progress(copied_bytes, total_bytes, target)
            target_handle.flush()
            os.fsync(target_handle.fileno())
        shutil.copystat(source, temporary)
        if target.exists() and not overwrite:
            raise FileExistsError(f"Export destination already exists: {target}")
        temporary.replace(target)
        return copied_bytes
    finally:
        temporary.unlink(missing_ok=True)


def _append_item(
    items: list[ExportItem],
    seen: set[Path],
    label: str,
    category: str,
    source_path: Path,
    relative_path: Path,
    default_selected: bool = True,
) -> None:
    source_path = source_path.expanduser().resolve()
    if source_path in seen:
        return
    seen.add(source_path)
    items.append(
        ExportItem(
            label=label,
            category=category,
            source_path=source_path,
            relative_path=relative_path,
            default_selected=default_selected,
        )
    )


def _note_csv_paths(safe_key: str, paths: list[Path]) -> list[tuple[Path, Path]]:
    if len(paths) == 1:
        return [(Path("notes") / f"{safe_key}.csv", paths[0])]
    return [
        (Path("notes") / f"{safe_key}-{_export_file_stem(path.stem, fallback='notes')}.csv", path)
        for path in paths
    ]


def _safe_filename(name: str) -> str:
    stem = _export_file_stem(Path(name).stem, fallback="file")
    suffix = Path(name).suffix.lower()
    return f"{stem}{suffix or '.mid'}"


def _export_file_stem(value: str, fallback: str) -> str:
    return safe_file_stem(_export_slug(value), fallback=fallback)


def _export_slug(value: str) -> str:
    cleaned = []
    previous_dash = False
    for character in value.strip().lower():
        if character.isalnum():
            cleaned.append(character)
            previous_dash = False
        elif not previous_dash:
            cleaned.append("-")
            previous_dash = True
    return "".join(cleaned).strip("-")
