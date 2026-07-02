import os
from pathlib import Path

import pytest


pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication

from pitchstems.gui_widgets import DropZone, FretboardNoteMapWidget, PianoChordWidget


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

    labels_by_pitch_class = {pitch % 12: name for _rect, pitch, name in widget._key_hitboxes}
    assert labels_by_pitch_class[3] == "D#"
    assert labels_by_pitch_class[8] == "G#"
    assert labels_by_pitch_class[10] == "A#"


def test_piano_chord_widget_set_notes_supports_scale_display() -> None:
    _app()
    widget = PianoChordWidget()

    widget.set_notes("D Pelog", ["D", "D#", "F", "A", "A#"], "Theory scale")

    assert widget.chord_label == "D Pelog"
    assert widget.source_label == "Theory scale"
    assert widget.pitch_classes == {2, 3, 5, 9, 10}
    assert "D - D# - F - A - A#" in widget.toolTip()


def test_piano_chord_widget_maps_double_sharp_to_sounding_key() -> None:
    _app()
    widget = PianoChordWidget()

    widget.set_chord("A#add4(no5)/D#", ["A#", "C##", "D#"], "Inspector")

    assert widget.pitch_classes == {2, 3, 10}


def test_piano_and_fretboard_widgets_accept_note_colours() -> None:
    _app()
    piano = PianoChordWidget()
    fretboard = FretboardNoteMapWidget()

    piano.set_note_colours({0: "#f97316", 4: "#2563eb"})
    fretboard.set_note_colours({0: "#f97316", 4: "#2563eb"})

    assert piano.note_colours == {0: "#f97316", 4: "#2563eb"}
    assert fretboard.note_colours == {0: "#f97316", 4: "#2563eb"}


class _MouseEvent:
    def __init__(self, position: QPointF, modifiers=Qt.NoModifier) -> None:
        self._position = position
        self._modifiers = modifiers
        self.accepted = False

    def button(self):
        return Qt.LeftButton

    def position(self) -> QPointF:
        return self._position

    def modifiers(self):
        return self._modifiers

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

    c_key = next(rect for rect, pitch, _name in widget._key_hitboxes if pitch == 48)
    widget.mousePressEvent(_MouseEvent(QPointF(c_key.center().x(), c_key.bottom() - 2)))

    assert clicked == [(48, "C")]


def test_piano_chord_widget_clicks_unhighlighted_key() -> None:
    app = _app()
    widget = PianoChordWidget()
    clicked = []
    widget.on_note_clicked = lambda pitch, name: clicked.append((pitch, name))
    widget.set_chord("C", ["C", "E", "G"], "Inspector")
    widget.resize(280, 100)
    widget.show()
    app.processEvents()

    d_key = next(rect for rect, pitch, _name in widget._key_hitboxes if pitch == 50)
    widget.mousePressEvent(_MouseEvent(QPointF(d_key.center().x(), d_key.bottom() - 2)))

    assert clicked == [(50, "D")]


def test_piano_chord_widget_preview_range_controls_visible_keys() -> None:
    app = _app()
    widget = PianoChordWidget()
    widget.set_chord("C", ["C", "E", "G"], "Inspector")
    widget.set_preview_range(60, 64)
    widget.resize(280, 100)
    widget.show()
    app.processEvents()

    keys = [(pitch, name) for _rect, pitch, name in widget._key_hitboxes]

    assert keys == [(60, "C4"), (62, "D4"), (64, "E4"), (61, "C#4"), (63, "Eb4")]


def test_piano_chord_widget_ctrl_click_cycles_note_constraint() -> None:
    app = _app()
    widget = PianoChordWidget()
    changed = []
    widget.on_note_constraint_changed = lambda pitch_class, state: changed.append((pitch_class, state))
    widget.set_chord("C", ["C", "E", "G"], "Inspector")
    widget.resize(280, 100)
    widget.show()
    app.processEvents()

    d_key = next(rect for rect, pitch, _name in widget._key_hitboxes if pitch == 50)
    point = QPointF(d_key.center().x(), d_key.bottom() - 2)

    widget.mousePressEvent(_MouseEvent(point, Qt.ControlModifier))
    widget.mousePressEvent(_MouseEvent(point, Qt.ControlModifier))
    widget.mousePressEvent(_MouseEvent(point, Qt.ControlModifier))

    assert changed == [(2, "force"), (2, "exclude"), (2, "auto")]
    assert widget.note_constraints == {}


def test_fretboard_note_map_widget_maps_notes_across_bass_frets() -> None:
    app = _app()
    widget = FretboardNoteMapWidget()
    widget.set_tuning("bass")
    widget.set_chord("C", ["C", "E", "G"], "Inspector", {0: {"root"}})
    widget.resize(360, 130)
    widget.show()
    app.processEvents()

    hit_pitch_classes = {pitch % 12 for _rect, pitch, _name in widget._note_hitboxes}

    assert widget.pitch_classes == {0, 4, 7}
    assert hit_pitch_classes == {0, 4, 7}
    assert widget.note_roles == {0: {"root"}}


def test_fretboard_note_map_widget_ctrl_click_cycles_note_constraint() -> None:
    app = _app()
    widget = FretboardNoteMapWidget()
    changed = []
    widget.on_note_constraint_changed = lambda pitch_class, state: changed.append((pitch_class, state))
    widget.set_chord("C", ["C", "E", "G"], "Inspector")
    widget.resize(360, 130)
    widget.show()
    app.processEvents()

    c_note = next(rect for rect, pitch, _name in widget._note_hitboxes if pitch % 12 == 0)

    widget.mousePressEvent(_MouseEvent(c_note.center(), Qt.ControlModifier))

    assert changed == [(0, "force")]
    assert widget.note_constraints == {0: "force"}


def test_fretboard_note_map_widget_clicks_unhighlighted_fret_note() -> None:
    app = _app()
    widget = FretboardNoteMapWidget()
    clicked = []
    widget.on_note_clicked = lambda pitch, name: clicked.append((pitch, name))
    widget.set_chord("C", ["C", "E", "G"], "Inspector")
    widget.resize(360, 130)
    widget.show()
    app.processEvents()

    unhighlighted = next(
        (rect, pitch, _name)
        for rect, pitch, _name in widget._fret_hitboxes
        if pitch % 12 not in widget.pitch_classes
    )

    widget.mousePressEvent(_MouseEvent(unhighlighted[0].center()))

    assert clicked
    assert clicked[-1][0] == unhighlighted[1]


def test_fretboard_note_map_widget_ctrl_clicks_unhighlighted_fret_constraint() -> None:
    app = _app()
    widget = FretboardNoteMapWidget()
    changed = []
    widget.on_note_constraint_changed = lambda pitch_class, state: changed.append((pitch_class, state))
    widget.set_chord("C", ["C", "E", "G"], "Inspector")
    widget.resize(360, 130)
    widget.show()
    app.processEvents()

    unhighlighted = next(
        (rect, pitch, _name)
        for rect, pitch, _name in widget._fret_hitboxes
        if pitch % 12 not in widget.pitch_classes
    )

    widget.mousePressEvent(_MouseEvent(unhighlighted[0].center(), Qt.ControlModifier))

    assert changed == [(unhighlighted[1] % 12, "force")]
    assert widget.note_constraints == {unhighlighted[1] % 12: "force"}


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
