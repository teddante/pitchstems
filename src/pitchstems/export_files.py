from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from pitchstems.filename_safety import safe_file_stem
from pitchstems.pipeline import PipelineResult


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


def build_export_items(result: PipelineResult) -> list[ExportItem]:
    items: list[ExportItem] = []
    seen: set[Path] = set()

    manifest = result.project_dir / "pitchstems.project.json"
    if manifest.is_file():
        _append_item(items, seen, "Project manifest", "Project", manifest, Path(manifest.name))

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


def copy_export_items(items: list[ExportItem], destination: Path) -> ExportSummary:
    if not items:
        raise ValueError("Choose at least one file to export.")

    destination = destination.expanduser().resolve()
    relative_paths: list[Path] = []
    for item in items:
        target = destination / item.relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item.source_path, target)
        relative_paths.append(item.relative_path)
    return ExportSummary(
        destination=destination,
        file_count=len(items),
        relative_paths=tuple(relative_paths),
    )


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
