import os
from pathlib import Path

import pytest


pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from pitchstems.gui_widgets import DropZone, PianoChordWidget  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_piano_chord_widget_accepts_flat_chord_tones() -> None:
    _app()
    widget = PianoChordWidget()

    widget.set_chord("Gb", ["Gb", "Bb", "Db"], "Inspector")

    assert widget.chord_label == "Gb"
    assert widget.pitch_classes == {1, 6, 10}
    assert "Gb - Bb - Db" in widget.toolTip()


def test_drop_zone_project_label_uses_bounded_project_text(tmp_path: Path) -> None:
    _app()
    widget = DropZone()
    project_dir = tmp_path / "example.pitchstems"
    source = project_dir / "audio" / "source.mp3"

    widget.set_project_file(project_dir, source)

    assert "Project" in widget.text()
    assert "example.pitchstems" in widget.text()
    assert str(source) in widget.toolTip()


class _Url:
    def __init__(self, path: Path) -> None:
        self.path = path

    def isLocalFile(self) -> bool:
        return True

    def toLocalFile(self) -> str:
        return str(self.path)


class _MimeData:
    def __init__(self, path: Path) -> None:
        self.path = path

    def urls(self):
        return [_Url(self.path)]


class _DropEvent:
    def __init__(self, path: Path) -> None:
        self.path = path

    def mimeData(self):
        return _MimeData(self.path)


def test_drop_zone_invalid_drop_clears_previous_audio_path(tmp_path: Path) -> None:
    _app()
    widget = DropZone()
    valid = tmp_path / "song.wav"
    invalid = tmp_path / "notes.txt"
    valid.write_bytes(b"RIFF")
    invalid.write_text("not audio", encoding="utf-8")
    widget.set_audio_file(valid)

    widget.dropEvent(_DropEvent(invalid))

    assert widget.path is None
    assert "Unsupported audio file type" in widget.text()
