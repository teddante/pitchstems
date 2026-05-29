import json
from pathlib import Path

from pitchstems.pipeline import PipelineResult
from pitchstems.project_store import (
    PROJECT_FILENAME,
    load_pipeline_result,
    load_project_manifest,
    save_project_manifest,
    _write_json_atomic,
)
from pitchstems.separation import SeparationOptions, StemResult
from pitchstems.transcription import MidiOptions, MidiResult


def test_save_and_load_project_manifest_round_trip(tmp_path: Path) -> None:
    project_dir = tmp_path / "song.pitchstems"
    normalized = project_dir / "work" / "song.wav"
    stem = project_dir / "stems" / "song_bass.wav"
    midi = project_dir / "midi" / "bass" / "song_bass.mid"
    combined = project_dir / "export" / "song_combined.mid"
    zip_path = project_dir / "song_pitchstems.zip"
    for path in [normalized, stem, midi, combined, zip_path]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("placeholder", encoding="utf-8")

    result = PipelineResult(
        project_dir=project_dir,
        normalized_audio=normalized,
        stems=[StemResult("bass", stem)],
        midi_files=[MidiResult("bass", midi)],
        combined_midi=combined,
        zip_path=zip_path,
        source_audio=tmp_path / "source.mp3",
    )

    manifest_path = save_project_manifest(
        result,
        separation_options=SeparationOptions(device="cuda:0"),
        midi_options=MidiOptions(onset_threshold=0.42),
        midi_stems={"bass"},
        generate_midi=True,
        midi_policy="all",
        create_zip=True,
        track_visibility={"bass": True},
        track_analysis_enabled={"bass": True},
        track_audio_enabled={"bass": True},
        track_audio_volume={"bass": 80},
        track_midi_enabled={"bass": False},
        track_midi_volume={"bass": 70},
        notation_spelling="flat",
        playhead_seconds=12.5,
        chord_overrides=[
            {"start": 10.0, "end": 12.0, "label": "Gmaj9", "confidence": 0.93}
        ],
        chord_removals=[{"start": 8.0, "end": 9.5}],
    )
    loaded = load_pipeline_result(manifest_path)
    manifest = load_project_manifest(manifest_path)

    assert manifest_path == project_dir / PROJECT_FILENAME
    assert loaded.project_dir == project_dir
    assert loaded.normalized_audio == normalized
    assert loaded.stems == [StemResult("bass", stem)]
    assert loaded.midi_files == [MidiResult("bass", midi)]
    assert loaded.combined_midi == combined
    assert loaded.zip_path == zip_path
    assert loaded.source_audio == tmp_path / "source.mp3"
    assert manifest["editor"]["chord_overrides"] == [
        {"start": 10.0, "end": 12.0, "label": "Gmaj9", "confidence": 0.93}
    ]
    assert manifest["editor"]["chord_removals"] == [{"start": 8.0, "end": 9.5}]
    assert manifest["editor"]["track_analysis_enabled"] == {"bass": True}
    assert manifest["editor"]["notation_spelling"] == "flat"


def test_write_json_atomic_replaces_existing_manifest_without_temp_file(tmp_path: Path) -> None:
    manifest_path = tmp_path / PROJECT_FILENAME
    manifest_path.write_text('{"old": true}', encoding="utf-8")

    _write_json_atomic(manifest_path, {"new": True})

    assert json.loads(manifest_path.read_text(encoding="utf-8")) == {"new": True}
    assert not list(tmp_path.glob(f".{PROJECT_FILENAME}.*.tmp"))


def test_load_project_manifest_rejects_incomplete_project(tmp_path: Path) -> None:
    manifest_path = tmp_path / PROJECT_FILENAME
    manifest_path.write_text(
        json.dumps({"format": "pitchstems-project", "format_version": 1}),
        encoding="utf-8",
    )

    try:
        load_project_manifest(manifest_path)
    except ValueError as exc:
        assert "missing required project field" in str(exc)
    else:
        raise AssertionError("Expected incomplete project to be rejected")


def test_load_project_manifest_rejects_bad_format_version(tmp_path: Path) -> None:
    manifest_path = tmp_path / PROJECT_FILENAME
    manifest_path.write_text(
        json.dumps(
            {
                "format": "pitchstems-project",
                "format_version": "abc",
                "normalized_audio": "work/source.wav",
                "stems": [],
                "midi_files": [],
            }
        ),
        encoding="utf-8",
    )

    try:
        load_project_manifest(manifest_path)
    except ValueError as exc:
        assert "invalid PitchStems project format version" in str(exc)
    else:
        raise AssertionError("Expected bad project format version to be rejected")


def test_load_project_manifest_rejects_malformed_asset_entries(tmp_path: Path) -> None:
    manifest_path = tmp_path / PROJECT_FILENAME
    manifest_path.write_text(
        json.dumps(
            {
                "format": "pitchstems-project",
                "format_version": 2,
                "normalized_audio": "work/source.wav",
                "stems": [{"name": "bass"}],
                "midi_files": [{"stem": "bass", "path": "midi/bass.mid"}],
            }
        ),
        encoding="utf-8",
    )

    try:
        load_pipeline_result(manifest_path)
    except ValueError as exc:
        assert "invalid stem entry" in str(exc)
    else:
        raise AssertionError("Expected malformed stem entry to be rejected")


def test_load_project_manifest_rejects_malformed_optional_paths(tmp_path: Path) -> None:
    manifest_path = tmp_path / PROJECT_FILENAME
    manifest_path.write_text(
        json.dumps(
            {
                "format": "pitchstems-project",
                "format_version": 2,
                "source_audio": ["not", "a", "path"],
                "normalized_audio": "work/source.wav",
                "stems": [],
                "midi_files": [],
            }
        ),
        encoding="utf-8",
    )

    try:
        load_project_manifest(manifest_path)
    except ValueError as exc:
        assert "invalid project path field: source_audio" in str(exc)
    else:
        raise AssertionError("Expected malformed optional path to be rejected")


def test_load_project_manifest_rejects_relative_paths_outside_project(tmp_path: Path) -> None:
    manifest_path = tmp_path / PROJECT_FILENAME
    manifest_path.write_text(
        json.dumps(
            {
                "format": "pitchstems-project",
                "format_version": 2,
                "normalized_audio": "../outside.wav",
                "stems": [],
                "midi_files": [],
            }
        ),
        encoding="utf-8",
    )

    try:
        load_project_manifest(manifest_path)
    except ValueError as exc:
        assert "outside the project folder: normalized_audio" in str(exc)
    else:
        raise AssertionError("Expected escaping relative project path to be rejected")


def test_load_project_manifest_allows_absolute_external_source_audio(tmp_path: Path) -> None:
    manifest_path = tmp_path / PROJECT_FILENAME
    external_source = tmp_path.parent / "source.mp3"
    manifest_path.write_text(
        json.dumps(
            {
                "format": "pitchstems-project",
                "format_version": 2,
                "source_audio": str(external_source),
                "normalized_audio": "work/source.wav",
                "stems": [],
                "midi_files": [],
            }
        ),
        encoding="utf-8",
    )

    manifest = load_project_manifest(manifest_path)

    assert manifest["source_audio"] == str(external_source)


def test_load_project_manifest_migrates_v1_editor_defaults(tmp_path: Path) -> None:
    project_dir = tmp_path / "song.pitchstems"
    manifest_path = project_dir / PROJECT_FILENAME
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "format": "pitchstems-project",
                "format_version": 1,
                "normalized_audio": "work/source.wav",
                "stems": [],
                "midi_files": [],
            }
        ),
        encoding="utf-8",
    )

    manifest = load_project_manifest(manifest_path)

    assert manifest["format_version"] == 2
    assert manifest["editor"]["notation_spelling"] == "auto"
    assert manifest["editor"]["chord_overrides"] == []
