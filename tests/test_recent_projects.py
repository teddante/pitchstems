from pathlib import Path, PureWindowsPath

from pitchstems.project_store import PROJECT_FILENAME
from pitchstems.recent_projects import (
    normalize_recent_project_paths,
    recent_project_label,
    remember_recent_project,
    remove_recent_project,
    short_path,
)


def test_normalize_recent_project_paths_accepts_single_string_and_deduplicates() -> None:
    paths = normalize_recent_project_paths([r"C:\Music\Song.pitchstems\pitchstems_project.json", r"c:\music\song.pitchstems\pitchstems_project.json"])

    assert paths == [Path(r"C:\Music\Song.pitchstems\pitchstems_project.json")]
    assert normalize_recent_project_paths(r"C:\One\project.json") == [Path(r"C:\One\project.json")]


def test_recent_project_label_uses_project_folder_for_standard_manifest() -> None:
    manifest = PureWindowsPath(r"C:\Users\edwar\PitchStems Projects\song.pitchstems") / PROJECT_FILENAME

    assert recent_project_label(manifest) == r"song.pitchstems  (C:\Users\edwar\PitchStems Projects)"


def test_recent_project_label_handles_nonstandard_manifest_name() -> None:
    manifest = PureWindowsPath(r"C:\Projects\song") / "custom.json"

    assert recent_project_label(manifest) == r"custom.json  (C:\Projects\song)"


def test_short_path_elides_from_the_left() -> None:
    assert short_path(PureWindowsPath(r"C:\a\very\long\folder\name"), max_length=12) == r"...lder\name"


def test_remember_recent_project_moves_existing_manifest_to_front(tmp_path: Path) -> None:
    first = tmp_path / "first.pitchstems" / PROJECT_FILENAME
    second_project = tmp_path / "second.pitchstems"
    second = second_project / PROJECT_FILENAME
    first.parent.mkdir()
    second.parent.mkdir()

    recent = remember_recent_project([first, second], second_project)

    assert recent == [second.resolve(), first]


def test_remove_recent_project_removes_matching_manifest(tmp_path: Path) -> None:
    keep = tmp_path / "keep.pitchstems" / PROJECT_FILENAME
    remove = tmp_path / "remove.pitchstems" / PROJECT_FILENAME
    keep.parent.mkdir()
    remove.parent.mkdir()

    assert remove_recent_project([keep, remove], remove) == [keep]
