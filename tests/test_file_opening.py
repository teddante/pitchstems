from pathlib import Path

import pytest

from pitchstems.file_opening import open_folder


def test_open_folder_creates_target_and_calls_opener(tmp_path: Path) -> None:
    opened = []
    target = tmp_path / "new-folder"

    result = open_folder(target, opener=opened.append)

    assert result == target
    assert target.is_dir()
    assert opened == [str(target)]


def test_open_folder_reports_unsupported_platform(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delattr("pitchstems.file_opening.os.startfile", raising=False)

    with pytest.raises(RuntimeError, match="not supported"):
        open_folder(tmp_path / "folder")
