from __future__ import annotations

from pathlib import Path

from pitchstems.gui_project_flow import set_audio_path


class _StatusBar:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def showMessage(self, message: str, _timeout: int) -> None:
        self.messages.append(message)


class _DropZone:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.reset_count = 0

    def set_audio_file(self, path: Path) -> None:
        self.path = path

    def reset_prompt(self) -> None:
        self.path = None
        self.reset_count += 1


class _Window:
    def __init__(self, previous_path: Path) -> None:
        self.drop_zone = _DropZone(previous_path)
        self.logs: list[str] = []
        self.status = _StatusBar()
        self.reset_paths: list[Path] = []

    def append_log(self, message: str) -> None:
        self.logs.append(message)

    def statusBar(self) -> _StatusBar:
        return self.status

    def reset_stage_state(self, path: Path) -> None:
        self.reset_paths.append(path)


def test_set_audio_path_invalid_selection_clears_previous_audio_path(tmp_path: Path) -> None:
    previous = tmp_path / "previous.wav"
    invalid = tmp_path / "notes.txt"
    previous.write_bytes(b"RIFF")
    invalid.write_text("not audio", encoding="utf-8")
    window = _Window(previous)

    set_audio_path(window, invalid)

    assert window.drop_zone.path is None
    assert window.drop_zone.reset_count == 1
    assert window.reset_paths == []
    assert any("Unsupported audio file type" in message for message in window.logs)
