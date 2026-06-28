import json
from pathlib import Path

import pytest

from pitchstems.audio_clip import AudioClipRange
from pitchstems.pipeline import PipelineResult
from pitchstems.project_store import (
    PROJECT_FILENAME,
    load_pipeline_result,
    load_project_manifest,
    save_failed_project_manifest,
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
        source_clip=AudioClipRange(4.0, 12.25),
        original_source_audio=tmp_path / "original.mp3",
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
    assert loaded.stems == [StemResult("bass", stem, "bass")]
    assert loaded.midi_files == [MidiResult("bass", midi, "bass")]
    assert loaded.combined_midi == combined
    assert loaded.zip_path == zip_path
    assert loaded.source_audio == tmp_path / "source.mp3"
    assert loaded.source_clip == AudioClipRange(4.0, 12.25)
    assert loaded.original_source_audio == tmp_path / "original.mp3"
    assert manifest["settings"]["source_clip"]["original_source_audio"] == str(tmp_path / "original.mp3")
    assert manifest["settings"]["source_clip"]["duration_seconds"] == 8.25
    assert manifest["stems"][0]["stem_id"] == "bass"
    assert manifest["midi_files"][0]["stem_id"] == "bass"
    assert manifest["editor"]["chord_overrides"] == [
        {"start": 10.0, "end": 12.0, "label": "Gmaj9", "confidence": 0.93}
    ]
    assert manifest["editor"]["chord_removals"] == [{"start": 8.0, "end": 9.5}]
    assert manifest["editor"]["track_analysis_enabled"] == {"bass": True}
    assert manifest["editor"]["notation_spelling"] == "flat"


def test_manifest_saves_and_loads_stem_ids(tmp_path: Path) -> None:
    project_dir = tmp_path / "song.pitchstems"
    normalized = project_dir / "work" / "song.wav"
    source = project_dir / "audio" / "song.wav"
    stem = project_dir / "stems" / "vocals.wav"
    midi = project_dir / "midi" / "vocals-lead" / "x.mid"
    for path in [normalized, source, stem, midi]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("placeholder", encoding="utf-8")
    result = PipelineResult(
        project_dir=project_dir,
        normalized_audio=normalized,
        stems=[StemResult("Vocals Lead", stem, "vocals-lead")],
        midi_files=[MidiResult("Vocals Lead", midi, "vocals-lead")],
        combined_midi=None,
        zip_path=None,
        source_audio=source,
    )

    save_project_manifest(result)
    manifest = load_project_manifest(result.project_dir)
    loaded = load_pipeline_result(result.project_dir)

    assert manifest["stems"][0]["stem_id"] == "vocals-lead"
    assert manifest["midi_files"][0]["stem_id"] == "vocals-lead"
    assert loaded.stems == [StemResult("Vocals Lead", stem, "vocals-lead")]
    assert loaded.midi_files == [MidiResult("Vocals Lead", midi, "vocals-lead")]


def test_load_pipeline_result_rejects_failed_manifest_with_last_error(tmp_path: Path) -> None:
    project_dir = tmp_path / "song.pitchstems"
    source = project_dir / "audio" / "song.wav"
    normalized = project_dir / "work" / "song.wav"
    source.parent.mkdir(parents=True)
    normalized.parent.mkdir(parents=True)
    source.write_bytes(b"source")
    normalized.write_bytes(b"wav")
    save_failed_project_manifest(project_dir, source, normalized, "native failed")

    with pytest.raises(ValueError, match="Project processing failed: native failed"):
        load_pipeline_result(project_dir)


def test_write_json_atomic_replaces_existing_manifest_without_temp_file(tmp_path: Path) -> None:
    manifest_path = tmp_path / PROJECT_FILENAME
    manifest_path.write_text('{"old": true}', encoding="utf-8")

    _write_json_atomic(manifest_path, {"new": True})

    assert json.loads(manifest_path.read_text(encoding="utf-8")) == {"new": True}
    assert not list(tmp_path.glob(f".{PROJECT_FILENAME}.*.tmp"))


def test_save_project_manifest_recovers_from_malformed_existing_manifest(tmp_path: Path) -> None:
    project_dir = tmp_path / "song.pitchstems"
    project_dir.mkdir()
    manifest_path = project_dir / PROJECT_FILENAME
    manifest_path.write_text(json.dumps(["not", "a", "manifest"]), encoding="utf-8")
    normalized = project_dir / "work" / "song.wav"

    saved_path = save_project_manifest(
        PipelineResult(
            project_dir=project_dir,
            normalized_audio=normalized,
            stems=[],
            midi_files=[],
            combined_midi=None,
            zip_path=None,
            source_audio=None,
        )
    )

    assert saved_path == manifest_path
    manifest = load_project_manifest(manifest_path)
    assert manifest["format"] == "pitchstems-project"
    assert manifest["normalized_audio"] == "work/song.wav"


def test_save_project_manifest_ignores_non_pitchstems_existing_json_object(tmp_path: Path) -> None:
    project_dir = tmp_path / "song.pitchstems"
    project_dir.mkdir()
    manifest_path = project_dir / PROJECT_FILENAME
    manifest_path.write_text(
        json.dumps({"created_at": "not ours", "settings": [], "editor": []}),
        encoding="utf-8",
    )
    normalized = project_dir / "work" / "song.wav"

    save_project_manifest(
        PipelineResult(
            project_dir=project_dir,
            normalized_audio=normalized,
            stems=[],
            midi_files=[],
            combined_midi=None,
            zip_path=None,
            source_audio=None,
        )
    )

    manifest = load_project_manifest(manifest_path)
    assert manifest["format"] == "pitchstems-project"
    assert manifest["created_at"] != "not ours"
    assert manifest["settings"] == {
        "create_zip": None,
        "generate_midi": None,
        "midi": {},
        "midi_policy": None,
        "midi_stems": [],
        "separation": {},
    }


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


def test_load_project_manifest_rejects_non_object_json_root(tmp_path: Path) -> None:
    manifest_path = tmp_path / PROJECT_FILENAME
    manifest_path.write_text(json.dumps(["not", "a", "manifest"]), encoding="utf-8")

    try:
        load_project_manifest(manifest_path)
    except ValueError as exc:
        assert "is not a PitchStems project" in str(exc)
    else:
        raise AssertionError("Expected non-object project JSON to be rejected")


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


def test_load_project_manifest_rejects_empty_required_asset_paths(tmp_path: Path) -> None:
    manifest_path = tmp_path / PROJECT_FILENAME
    manifest_path.write_text(
        json.dumps(
            {
                "format": "pitchstems-project",
                "format_version": 2,
                "normalized_audio": "",
                "stems": [],
                "midi_files": [],
            }
        ),
        encoding="utf-8",
    )

    try:
        load_project_manifest(manifest_path)
    except ValueError as exc:
        assert "empty project path field: normalized_audio" in str(exc)
    else:
        raise AssertionError("Expected empty required project path to be rejected")


def test_load_project_manifest_rejects_blank_stem_and_midi_names(tmp_path: Path) -> None:
    manifest_path = tmp_path / PROJECT_FILENAME
    manifest_path.write_text(
        json.dumps(
            {
                "format": "pitchstems-project",
                "format_version": 2,
                "normalized_audio": "work/source.wav",
                "stems": [{"name": " ", "path": "stems/bass.wav"}],
                "midi_files": [{"stem": "", "path": "midi/bass.mid"}],
            }
        ),
        encoding="utf-8",
    )

    try:
        load_project_manifest(manifest_path)
    except ValueError as exc:
        assert "invalid stem entry at index 0" in str(exc)
    else:
        raise AssertionError("Expected blank generated asset name to be rejected")


def test_load_project_manifest_rejects_unsafe_stem_and_midi_names(tmp_path: Path) -> None:
    manifest_path = tmp_path / PROJECT_FILENAME
    manifest_path.write_text(
        json.dumps(
            {
                "format": "pitchstems-project",
                "format_version": 2,
                "normalized_audio": "work/source.wav",
                "stems": [{"name": "../vocals", "path": "stems/vocals.wav"}],
                "midi_files": [{"stem": "lead:guitar", "path": "midi/guitar.mid"}],
            }
        ),
        encoding="utf-8",
    )

    try:
        load_project_manifest(manifest_path)
    except ValueError as exc:
        assert "unsafe stem name" in str(exc)
    else:
        raise AssertionError("Expected unsafe generated asset names to be rejected")


def test_load_project_manifest_rejects_names_that_collapse_to_fallback_key(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / PROJECT_FILENAME
    manifest_path.write_text(
        json.dumps(
            {
                "format": "pitchstems-project",
                "format_version": 2,
                "normalized_audio": "work/source.wav",
                "stems": [{"name": "___", "path": "stems/stem.wav"}],
                "midi_files": [],
            }
        ),
        encoding="utf-8",
    )

    try:
        load_project_manifest(manifest_path)
    except ValueError as exc:
        assert "unsafe stem name" in str(exc)
    else:
        raise AssertionError("Expected fallback-only generated asset name to be rejected")


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


def test_load_project_manifest_rejects_absolute_generated_assets_outside_project(tmp_path: Path) -> None:
    manifest_path = tmp_path / PROJECT_FILENAME
    external_stem = tmp_path.parent / "external_bass.wav"
    manifest_path.write_text(
        json.dumps(
            {
                "format": "pitchstems-project",
                "format_version": 2,
                "source_audio": str(tmp_path.parent / "source.mp3"),
                "normalized_audio": "work/source.wav",
                "stems": [{"name": "bass", "path": str(external_stem)}],
                "midi_files": [],
            }
        ),
        encoding="utf-8",
    )

    try:
        load_project_manifest(manifest_path)
    except ValueError as exc:
        assert "outside the project folder: stems[0].path" in str(exc)
    else:
        raise AssertionError("Expected external generated project asset to be rejected")


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
