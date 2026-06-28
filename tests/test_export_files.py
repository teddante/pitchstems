from pathlib import Path

import pytest

from pitchstems.export_files import build_export_items, copy_export_items
from pitchstems.pipeline import PipelineResult
from pitchstems.separation import StemResult
from pitchstems.transcription import MidiResult


def _write(path: Path, content: bytes = b"data") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_build_export_items_includes_available_project_outputs(tmp_path: Path) -> None:
    project_dir = tmp_path / "song.pitchstems"
    manifest = _write(project_dir / "pitchstems.project.json", b"manifest")
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
        ("Project", "pitchstems.project.json"),
        ("Source Audio", "audio/song.mp3"),
        ("Stems", "stems/bass.wav"),
        ("MIDI", "midi/bass.mid"),
        ("Notes CSV", "notes/bass.csv"),
        ("Combined MIDI", "midi/song-combined.mid"),
    ]
    assert {manifest, source, notes}.issubset({item.source_path for item in items})
    default_by_category = {item.category: item.default_selected for item in items}
    assert default_by_category["Project"]
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


def test_copy_export_items_copies_selected_files_and_overwrites(tmp_path: Path) -> None:
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

    summary = copy_export_items(selected, destination)

    assert summary.file_count == 3
    assert summary.destination == destination.resolve()
    assert [path.as_posix() for path in summary.relative_paths] == [
        "pitchstems.project.json",
        "stems/bass.wav",
        "midi/bass.mid",
    ]
    assert (destination / "pitchstems.project.json").read_bytes() == b"manifest"
    assert (destination / "stems" / "bass.wav").read_bytes() == b"new"
    assert (destination / "midi" / "bass.mid").read_bytes() == b"midi"
    assert not (destination / "audio" / "song.mp3").exists()


def test_copy_export_items_rejects_empty_selection(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Choose at least one file"):
        copy_export_items([], tmp_path / "exports")
