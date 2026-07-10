from pathlib import Path

import pytest

from pitchstems.export_files import (
    ExportCancelledError,
    ExportItem,
    build_export_items,
    copy_export_items,
    export_collisions,
)
from pitchstems.pipeline_models import MidiResult, PipelineResult, StemResult


def _write(path: Path, content: bytes = b"data") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_build_export_items_includes_available_project_outputs(tmp_path: Path) -> None:
    project_dir = tmp_path / "song.pitchstems"
    _write(project_dir / "pitchstems.project.json", b"manifest")
    source = _write(project_dir / "audio" / "song.mp3", b"source")
    stem = _write(project_dir / "stems" / "song_bass.wav", b"stem")
    midi = _write(project_dir / "midi" / "bass" / "song_bass.mid", b"midi")
    notes = _write(project_dir / "midi" / "bass" / "song_bass_basic_pitch.csv", b"notes")
    combined = _write(project_dir / "export" / "song_combined.mid", b"combined")
    missing_stem = project_dir / "stems" / "missing.wav"

    result = PipelineResult(
        project_dir=project_dir,
        normalized_audio=project_dir / "work" / "song.wav",
        stems=[
            StemResult("bass", stem),
            StemResult("missing", missing_stem),
        ],
        midi_files=[MidiResult("bass", midi)],
        combined_midi=combined,
        zip_path=None,
        source_audio=source,
    )

    items = build_export_items(result)

    assert [(item.category, item.relative_path.as_posix()) for item in items] == [
        ("Source Audio", "audio/song.mp3"),
        ("Stems", "stems/bass.wav"),
        ("MIDI", "midi/bass.mid"),
        ("Notes CSV", "notes/bass.csv"),
        ("Combined MIDI", "midi/song-combined.mid"),
    ]
    assert {source, notes}.issubset({item.source_path for item in items})
    default_by_category = {item.category: item.default_selected for item in items}
    assert not default_by_category["Source Audio"]
    assert default_by_category["Stems"]


def test_build_export_items_names_multiple_note_csvs_safely(tmp_path: Path) -> None:
    project_dir = tmp_path / "song.pitchstems"
    midi = _write(project_dir / "midi" / "Lead Vocal" / "lead.mid")
    _write(project_dir / "midi" / "Lead Vocal" / "lead_notes.csv")
    _write(project_dir / "midi" / "Lead Vocal" / "lead_onsets.csv")
    result = PipelineResult(
        project_dir=project_dir,
        normalized_audio=project_dir / "work" / "song.wav",
        stems=[],
        midi_files=[MidiResult("Lead Vocal", midi)],
        combined_midi=None,
        zip_path=None,
    )

    note_paths = [
        item.relative_path.as_posix()
        for item in build_export_items(result)
        if item.category == "Notes CSV"
    ]

    assert note_paths == [
        "notes/lead-vocal-lead-notes.csv",
        "notes/lead-vocal-lead-onsets.csv",
    ]


def test_build_export_items_uses_windows_safe_export_filenames(tmp_path: Path) -> None:
    project_dir = tmp_path / "song.pitchstems"
    source = _write(project_dir / "audio" / "CON.wav")
    combined = _write(project_dir / "export" / "NUL.mid")
    midi = _write(project_dir / "midi" / "Lead" / "lead.mid")
    _write(project_dir / "midi" / "Lead" / "COM1.csv")
    _write(project_dir / "midi" / "Lead" / "AUX.csv")
    result = PipelineResult(
        project_dir=project_dir,
        normalized_audio=project_dir / "work" / "song.wav",
        stems=[],
        midi_files=[MidiResult("Lead", midi, stem_id="lead")],
        combined_midi=combined,
        zip_path=None,
        source_audio=source,
    )

    paths = [item.relative_path.as_posix() for item in build_export_items(result)]

    assert "audio/file_con.wav" in paths
    assert "midi/file_nul.mid" in paths
    assert "notes/lead-notes_com1.csv" in paths
    assert "notes/lead-notes_aux.csv" in paths


def test_copy_export_items_copies_selected_files_after_overwrite_is_confirmed(tmp_path: Path) -> None:
    project_dir = tmp_path / "song.pitchstems"
    _write(project_dir / "pitchstems.project.json", b"manifest")
    source = _write(project_dir / "audio" / "song.mp3", b"source")
    stem = _write(project_dir / "stems" / "song_bass.wav", b"new")
    midi = _write(project_dir / "midi" / "bass" / "song_bass.mid", b"midi")
    result = PipelineResult(
        project_dir=project_dir,
        normalized_audio=project_dir / "work" / "song.wav",
        stems=[StemResult("bass", stem)],
        midi_files=[MidiResult("bass", midi)],
        combined_midi=None,
        zip_path=None,
        source_audio=source,
    )
    selected = [item for item in build_export_items(result) if item.default_selected]
    destination = tmp_path / "exports"
    _write(destination / "stems" / "bass.wav", b"old")

    assert export_collisions(selected, destination) == (destination / "stems" / "bass.wav",)

    summary = copy_export_items(selected, destination, overwrite=True)

    assert summary.file_count == 2
    assert summary.destination == destination.resolve()
    assert [path.as_posix() for path in summary.relative_paths] == [
        "stems/bass.wav",
        "midi/bass.mid",
    ]
    assert not (destination / "pitchstems.project.json").exists()
    assert (destination / "stems" / "bass.wav").read_bytes() == b"new"
    assert (destination / "midi" / "bass.mid").read_bytes() == b"midi"
    assert not (destination / "audio" / "song.mp3").exists()


def test_copy_export_items_rejects_empty_selection(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Choose at least one file"):
        copy_export_items([], tmp_path / "exports")


def test_copy_export_items_refuses_unconfirmed_overwrite(tmp_path: Path) -> None:
    source = _write(tmp_path / "source.wav", b"new")
    destination = tmp_path / "exports"
    existing = _write(destination / "stems" / "bass.wav", b"old")
    item = ExportItem("Bass", "Stems", source, Path("stems/bass.wav"))

    with pytest.raises(FileExistsError, match="already exists"):
        copy_export_items([item], destination)

    assert existing.read_bytes() == b"old"


def test_copy_export_items_cancellation_removes_partial_file(tmp_path: Path) -> None:
    source = _write(tmp_path / "source.wav", b"x" * (2 * 1024 * 1024))
    destination = tmp_path / "exports"
    item = ExportItem("Bass", "Stems", source, Path("stems/bass.wav"))
    cancel = False

    def progress(_copied: int, _total: int, _target: Path) -> None:
        nonlocal cancel
        cancel = True

    with pytest.raises(ExportCancelledError):
        copy_export_items([item], destination, cancelled=lambda: cancel, progress=progress)

    assert not (destination / "stems" / "bass.wav").exists()
    assert not list(destination.rglob("*.tmp"))


@pytest.mark.parametrize("relative_path", [Path("../escaped.wav"), Path("/tmp/escaped.wav")])
def test_copy_export_items_rejects_paths_outside_destination(
    tmp_path: Path,
    relative_path: Path,
) -> None:
    source = _write(tmp_path / "source.wav")
    item = ExportItem("unsafe", "Stems", source, relative_path)

    with pytest.raises(ValueError, match="Export path"):
        copy_export_items([item], tmp_path / "exports")


def test_copy_export_items_rejects_case_insensitive_destination_collisions(tmp_path: Path) -> None:
    first = _write(tmp_path / "first.wav")
    second = _write(tmp_path / "second.wav")
    items = [
        ExportItem("first", "Stems", first, Path("stems/Bass.wav")),
        ExportItem("second", "Stems", second, Path("stems/bass.wav")),
    ]

    with pytest.raises(ValueError, match="same file"):
        copy_export_items(items, tmp_path / "exports")
