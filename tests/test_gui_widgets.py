import os
from pathlib import Path

import pytest


pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication

from pitchstems.gui_widgets import DropZone, PianoChordWidget


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_piano_chord_widget_accepts_flat_chord_tones() -> None:
    _app()
    widget = PianoChordWidget()

    widget.set_chord("Gb", ["Gb", "Bb", "Db"], "Inspector")

    assert widget.chord_label == "Gb"
    assert widget.pitch_classes == {1, 6, 10}
    assert "Gb - Bb - Db" in widget.toolTip()


def test_piano_chord_widget_tracks_preview_note_roles() -> None:
    _app()
    widget = PianoChordWidget()

    widget.set_chord("C", ["C", "E", "G"], "Preview bass E, top G", {4: {"bass"}, 7: {"top"}})

    assert widget.note_roles == {4: {"bass"}, 7: {"top"}}
    assert "Voicing:" in widget.toolTip()
    assert "bass" in widget.toolTip()
    assert "top" in widget.toolTip()


def test_piano_chord_widget_key_labels_follow_pitch_class_formatter() -> None:
    app = _app()
    widget = PianoChordWidget()
    widget.set_pitch_class_formatter(
        lambda pitch_class: {3: "D#", 8: "G#", 10: "A#"}.get(pitch_class, str(pitch_class))
    )
    widget.set_chord("A#", ["A#", "D#", "F"], "Inspector")
    widget.resize(280, 100)
    widget.show()
    app.processEvents()

    labels_by_pitch = {pitch_class: name for _rect, pitch_class, name in widget._key_hitboxes}
    assert labels_by_pitch[3] == "D#"
    assert labels_by_pitch[8] == "G#"
    assert labels_by_pitch[10] == "A#"


def test_piano_chord_widget_set_notes_supports_scale_display() -> None:
    _app()
    widget = PianoChordWidget()

    widget.set_notes("D Pelog", ["D", "D#", "F", "A", "A#"], "Theory scale")

    assert widget.chord_label == "D Pelog"
    assert widget.source_label == "Theory scale"
    assert widget.pitch_classes == {2, 3, 5, 9, 10}
    assert "D - D# - F - A - A#" in widget.toolTip()


class _MouseEvent:
    def __init__(self, position: QPointF) -> None:
        self._position = position
        self.accepted = False

    def button(self):
        return Qt.LeftButton

    def position(self) -> QPointF:
        return self._position

    def accept(self) -> None:
        self.accepted = True


def test_piano_chord_widget_clicks_highlighted_key() -> None:
    app = _app()
    widget = PianoChordWidget()
    clicked = []
    widget.on_note_clicked = lambda pitch, name: clicked.append((pitch, name))
    widget.set_chord("C", ["C", "E", "G"], "Inspector")
    widget.resize(280, 100)
    widget.show()
    app.processEvents()

    c_key = next(rect for rect, pitch_class, _name in widget._key_hitboxes if pitch_class == 0)
    widget.mousePressEvent(_MouseEvent(QPointF(c_key.center().x(), c_key.bottom() - 2)))

    assert clicked == [(60, "C")]


def test_piano_chord_widget_clicks_unhighlighted_key() -> None:
    app = _app()
    widget = PianoChordWidget()
    clicked = []
    widget.on_note_clicked = lambda pitch, name: clicked.append((pitch, name))
    widget.set_chord("C", ["C", "E", "G"], "Inspector")
    widget.resize(280, 100)
    widget.show()
    app.processEvents()

    d_key = next(rect for rect, pitch_class, _name in widget._key_hitboxes if pitch_class == 2)
    widget.mousePressEvent(_MouseEvent(QPointF(d_key.center().x(), d_key.bottom() - 2)))

    assert clicked == [(62, "D")]


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
