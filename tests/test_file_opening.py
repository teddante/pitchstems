from pathlib import Path

from pitchstems.file_opening import open_folder


def test_open_folder_creates_target_and_calls_opener(tmp_path: Path) -> None:
    opened = []
    target = tmp_path / "new-folder"

    result = open_folder(target, opener=opened.append)

    assert result == target
    assert target.is_dir()
    assert opened == [str(target)]


def test_open_folder_uses_cross_platform_qt_opener(tmp_path: Path, monkeypatch) -> None:
    opened = []
    monkeypatch.setattr("pitchstems.file_opening._qt_open_folder", lambda path: opened.append(path) or True)

    target = tmp_path / "folder"
    assert open_folder(target) == target
    assert opened == [target]
