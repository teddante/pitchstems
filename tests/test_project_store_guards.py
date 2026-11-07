import json
from pathlib import Path

import pytest

import pitchstems.project_store as project_store
from pitchstems.project_store import (
    PROJECT_FORMAT_VERSION,
    _migrate_manifest,
    find_project_manifest,
    load_pipeline_result,
    project_manifest_path,
    restore_project_manifest_backup,
)


def test_find_project_manifest_rejects_other_files(tmp_path: Path) -> None:
    other = tmp_path / "notes.json"
    other.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="Not a PitchStems project manifest"):
        find_project_manifest(other)


def test_restore_backup_rejects_non_object_snapshots(tmp_path: Path) -> None:
    project_dir = tmp_path / "song.pitchstems"
    project_dir.mkdir()
    backup = tmp_path / "backup.json"
    backup.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid manifest backup"):
        restore_project_manifest_backup(project_dir, backup)


def test_restore_backup_keeps_current_editor_state(tmp_path: Path) -> None:
    project_dir = tmp_path / "song.pitchstems"
    project_dir.mkdir()
    project_manifest_path(project_dir).write_text(
        json.dumps({"format": "pitchstems-project", "format_version": 2, "editor": {"chords": "kept"}, "settings": {"old": True}}),
        encoding="utf-8",
    )
    backup = tmp_path / "backup.json"
    backup.write_text(
        json.dumps({"format": "pitchstems-project", "format_version": 2, "settings": {"restored": True}}),
        encoding="utf-8",
    )

    restore_project_manifest_backup(project_dir, backup)

    manifest = json.loads(project_manifest_path(project_dir).read_text(encoding="utf-8"))
    assert manifest["settings"] == {"restored": True}
    assert manifest["editor"] == {"chords": "kept"}



def _envelope(**fields: object) -> dict[str, object]:
    return {"format": "pitchstems-project", "format_version": PROJECT_FORMAT_VERSION, **fields}


def test_migration_leaves_foreign_future_and_malformed_manifests_alone() -> None:
    assert _migrate_manifest(["not", "a", "dict"]) == ["not", "a", "dict"]  # type: ignore[arg-type]
    foreign = {"format": "other"}
    assert _migrate_manifest(foreign) == foreign
    bad_version = {"format": "pitchstems-project", "format_version": "soon"}
    assert _migrate_manifest(bad_version) == bad_version
    future = _envelope(format_version=PROJECT_FORMAT_VERSION + 1)
    assert _migrate_manifest(future) == future


def test_legacy_manifest_migrates_to_current_editor_defaults() -> None:
    legacy = {"format": "pitchstems-project", "format_version": 1, "editor": {"note_edits": [1]}}

    migrated = _migrate_manifest(legacy)

    assert migrated["format_version"] == PROJECT_FORMAT_VERSION
    assert migrated["settings"] == {}
    assert "note_edits" not in migrated["editor"]


def test_failed_projects_refuse_to_load_with_their_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(project_store, "_validate_manifest", lambda _path, _manifest: None)
    project_dir = tmp_path / "song.pitchstems"
    project_dir.mkdir()
    project_manifest_path(project_dir).write_text(
        json.dumps(_envelope(status="failed", last_error="FFmpeg missing")),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="FFmpeg missing"):
        load_pipeline_result(project_dir)
