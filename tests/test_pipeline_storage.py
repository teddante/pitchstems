from pathlib import Path
from zipfile import ZipFile

from pitchstems.pipeline import _remove_export_stem_copies, _zip_project_outputs
from pitchstems.separation import StemResult
from pitchstems.transcription import MidiResult


def test_zip_project_outputs_packages_canonical_assets_without_export_copies(tmp_path: Path) -> None:
    project_dir = tmp_path / "song.pitchstems"
    stems_dir = project_dir / "stems"
    midi_dir = project_dir / "midi" / "bass"
    export_dir = project_dir / "export"
    stems_dir.mkdir(parents=True)
    midi_dir.mkdir(parents=True)
    export_dir.mkdir()

    stem_path = stems_dir / "song_bass.wav"
    midi_path = midi_dir / "song_bass.mid"
    combined_path = export_dir / "song_combined.mid"
    manifest_path = project_dir / "pitchstems.project.json"
    zip_path = project_dir / "song_pitchstems.zip"
    stem_path.write_bytes(b"stem")
    midi_path.write_bytes(b"midi")
    combined_path.write_bytes(b"combined")
    manifest_path.write_text("{}", encoding="utf-8")

    _zip_project_outputs(
        project_dir,
        [StemResult("bass", stem_path)],
        [MidiResult("bass", midi_path)],
        combined_path,
        zip_path,
    )

    assert zip_path.is_file()
    assert not (export_dir / stem_path.name).exists()
    with ZipFile(zip_path) as archive:
        assert sorted(archive.namelist()) == [
            "midi/bass.mid",
            "midi/song_combined.mid",
            "pitchstems.project.json",
            "stems/song_bass.wav",
        ]


def test_remove_export_stem_copies_only_deletes_known_duplicate_stems(tmp_path: Path) -> None:
    project_dir = tmp_path / "song.pitchstems"
    stems_dir = project_dir / "stems"
    export_dir = project_dir / "export"
    stems_dir.mkdir(parents=True)
    export_dir.mkdir()

    stem_path = stems_dir / "song_bass.wav"
    duplicate_path = export_dir / stem_path.name
    unrelated_wav = export_dir / "manual_export.wav"
    stem_path.write_bytes(b"canonical")
    duplicate_path.write_bytes(b"duplicate")
    unrelated_wav.write_bytes(b"keep")

    _remove_export_stem_copies(export_dir, [StemResult("bass", stem_path)])

    assert stem_path.is_file()
    assert not duplicate_path.exists()
    assert unrelated_wav.is_file()
