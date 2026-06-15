from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from pitchstems.pipeline import PipelineResult
from pitchstems.separation import safe_stem_key


@dataclass(frozen=True)
class ExportItem:
    label: str
    category: str
    source_path: Path
    relative_path: Path


@dataclass(frozen=True)
class ExportSummary:
    destination: Path
    file_count: int


def build_export_items(result: PipelineResult) -> list[ExportItem]:
    items: list[ExportItem] = []
    seen: set[Path] = set()

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
    for item in items:
        target = destination / item.relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item.source_path, target)
    return ExportSummary(destination=destination, file_count=len(items))


def _append_item(
    items: list[ExportItem],
    seen: set[Path],
    label: str,
    category: str,
    source_path: Path,
    relative_path: Path,
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
        )
    )


def _note_csv_paths(safe_key: str, paths: list[Path]) -> list[tuple[Path, Path]]:
    if len(paths) == 1:
        return [(Path("notes") / f"{safe_key}.csv", paths[0])]
    return [
        (Path("notes") / f"{safe_key}-{safe_stem_key(path.stem)}.csv", path)
        for path in paths
    ]


def _safe_filename(name: str) -> str:
    stem = safe_stem_key(Path(name).stem)
    suffix = Path(name).suffix.lower()
    return f"{stem}{suffix or '.mid'}"
