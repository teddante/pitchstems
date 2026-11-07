import json
from pathlib import Path

import pytest

import pitchstems.midi_transaction as midi_transaction
import pitchstems.pipeline as pipeline
from pitchstems.pipeline import _MidiWorkspace


def test_safe_archive_path_accepts_relative_paths_only() -> None:
    assert pipeline._safe_archive_path(Path("stems") / "bass.wav") == "stems/bass.wav"

    for unsafe in [Path("/etc/passwd"), Path("stems/../secret.wav"), Path("")]:
        with pytest.raises(ValueError, match="safe relative path"):
            pipeline._safe_archive_path(unsafe)


def test_remove_new_project_dir_refuses_unsafe_targets(tmp_path: Path) -> None:
    output_root = tmp_path / "out"
    output_root.mkdir()

    with pytest.raises(ValueError, match="output root"):
        pipeline.remove_new_project_dir(output_root, output_root)
    with pytest.raises(ValueError, match="PitchStems project"):
        pipeline.remove_new_project_dir(output_root / "song", output_root)
    with pytest.raises(ValueError, match="inside the output root"):
        pipeline.remove_new_project_dir(tmp_path / "elsewhere.pitchstems", output_root)


def test_remove_new_project_dir_deletes_a_partial_project(tmp_path: Path) -> None:
    output_root = tmp_path / "out"
    project_dir = output_root / "song.pitchstems"
    (project_dir / "stems").mkdir(parents=True)
    (project_dir / "stems" / "bass.wav").write_bytes(b"")

    pipeline.remove_new_project_dir(project_dir, output_root)

    assert not project_dir.exists()
    assert output_root.exists()


def _workspace(tmp_path: Path) -> _MidiWorkspace:
    return _MidiWorkspace.from_project(tmp_path / "song.pitchstems", "Song")


def test_read_midi_transaction_rejects_corrupt_markers(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.project_dir.mkdir(parents=True)
    marker = workspace.transaction_path

    cases = {
        "not json": "{",
        "not an object": "[]",
        "unknown phase": json.dumps({"phase": "bogus", "generated_export_midi": [], "had_midi_dir": False}),
        "path traversal name": json.dumps(
            {"phase": "prepared", "generated_export_midi": ["../evil.mid"], "had_midi_dir": False}
        ),
        "non-bool flag": json.dumps({"phase": "prepared", "generated_export_midi": [], "had_midi_dir": "yes"}),
    }
    for text in cases.values():
        marker.write_text(text, encoding="utf-8")
        with pytest.raises(RuntimeError, match="transaction"):
            midi_transaction._read_midi_transaction(workspace)


def test_commit_without_marker_is_a_no_op(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.project_dir.mkdir(parents=True)

    pipeline._commit_midi_transaction(workspace)

    assert not workspace.transaction_path.exists()


def test_recover_without_marker_leaves_project_untouched(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.project_dir.mkdir(parents=True)
    workspace.midi_dir.mkdir()
    (workspace.midi_dir / "bass.mid").write_bytes(b"MThd")

    pipeline._recover_midi_transaction(workspace)

    assert (workspace.midi_dir / "bass.mid").read_bytes() == b"MThd"


def test_recover_fails_loudly_when_backup_is_missing(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.project_dir.mkdir(parents=True)
    midi_transaction._write_midi_transaction(workspace, "backed_up", set(), True)

    with pytest.raises(RuntimeError, match="backup is missing"):
        pipeline._recover_midi_transaction(workspace)


def test_legacy_recovery_restores_the_midi_backup(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.project_dir.mkdir(parents=True)
    workspace.backup_midi_dir.mkdir()
    (workspace.backup_midi_dir / "bass.mid").write_bytes(b"old")
    workspace.midi_dir.mkdir()
    (workspace.midi_dir / "partial.mid").write_bytes(b"new")

    midi_transaction._recover_midi_transaction(workspace)

    assert (workspace.midi_dir / "bass.mid").read_bytes() == b"old"
    assert not (workspace.midi_dir / "partial.mid").exists()
    assert not workspace.backup_midi_dir.exists()


def test_export_backup_replaces_partial_files_and_directories(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.project_dir.mkdir(parents=True)
    workspace.backup_export_dir.mkdir()
    (workspace.backup_export_dir / "keep.mid").write_bytes(b"keep")
    (workspace.backup_export_dir / "sub.mid").write_bytes(b"file")
    workspace.export_dir.mkdir()
    (workspace.export_dir / "keep.mid").write_bytes(b"partial")
    (workspace.export_dir / "sub.mid").mkdir()
    (workspace.export_dir / "sub.mid" / "junk.txt").write_bytes(b"x")

    midi_transaction._recover_midi_transaction(workspace)

    assert (workspace.export_dir / "keep.mid").read_bytes() == b"keep"
    assert (workspace.export_dir / "sub.mid").read_bytes() == b"file"


def test_symlinked_export_backup_is_rejected(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.project_dir.mkdir(parents=True)
    target = tmp_path / "elsewhere"
    target.mkdir()
    try:
        workspace.backup_export_dir.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks need extra privileges on this system")

    with pytest.raises(ValueError, match="must not be a symlink"):
        midi_transaction._recover_midi_transaction(workspace)


def test_project_guards_reject_root_outside_and_non_projects(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.project_dir.mkdir(parents=True)

    with pytest.raises(ValueError, match="must not be the project root"):
        midi_transaction._assert_project_child(workspace.project_dir, workspace.project_dir, "probe")
    with pytest.raises(ValueError, match="must stay inside the project folder"):
        midi_transaction._assert_project_child(workspace.project_dir, tmp_path / "outside.mid", "probe")
    with pytest.raises(ValueError, match="must be a PitchStems project"):
        midi_transaction._assert_project_workspace(tmp_path / "plain")
