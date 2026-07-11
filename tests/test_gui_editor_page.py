import os

import pytest


pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QLabel,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from pitchstems.gui_editor_page import build_editor_page
from pitchstems.gui_timeline import TimelineView
from pitchstems.gui_widgets import FretboardNoteMapWidget, PianoChordWidget


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class _EditorWindow:
    def __init__(self, width: int) -> None:
        self._width = width
        self.notation_spelling = QComboBox()
        self.chord_context = _wrapped_label("Sample: -", 64)
        self.chord_detector_help = _wrapped_label(
            "Harmony comes from the selected Chord tracks: MIDI note energy feeds chord detection.",
            0,
        )
        self.min_note_evidence_label = QLabel("Min note evidence: 0%")
        self.min_note_evidence_slider = QSlider(Qt.Horizontal)
        self.note_filter_help = _wrapped_label("Auto uses MIDI energy evidence.", 0)
        self.note_filter_list = QListWidget()
        self.preview_chord_button = QPushButton("Play Chord")
        self.use_chord_button = QPushButton("Use for Selection")
        self.delete_chord_button = QPushButton("Delete Chord")
        self.detect_chords_button = QPushButton("Detect Chords")
        self.revert_chord_edits_button = QPushButton("Revert All Chord Edits")
        self.reset_note_filter_button = QPushButton("Reset Evidence")
        self.inspect_chord_button = QPushButton("Inspect")
        self.piano_chord_view = PianoChordWidget()
        self.chord_fretboard_view = FretboardNoteMapWidget()
        self.chord_note_map_stack = QStackedWidget()
        self.chord_note_map_stack.addWidget(self.piano_chord_view)
        self.chord_note_map_stack.addWidget(self.chord_fretboard_view)
        self.chord_view_mode = QComboBox()
        self.chord_one_octave_button = QPushButton("1 Oct")
        self.note_map_colours = QCheckBox("Colours")
        self.preview_bass_note = QComboBox()
        self.preview_top_note = QComboBox()
        self.chord_list = QListWidget()
        self.theory_context = _wrapped_label("Theory: -", 54)
        self.theory_scale_view = PianoChordWidget()
        self.theory_fretboard_view = FretboardNoteMapWidget()
        self.theory_note_map_stack = QStackedWidget()
        self.theory_note_map_stack.addWidget(self.theory_scale_view)
        self.theory_note_map_stack.addWidget(self.theory_fretboard_view)
        self.theory_view_mode = QComboBox()
        self.theory_one_octave_button = QPushButton("1 Oct")
        self.theory_list = QListWidget()
        self.show_chromatic_scales = QCheckBox("Chromatic")
        self.preview_scale_button = QPushButton("Play Scale")
        self.preview_scale_pattern = QComboBox()
        self.scale_chords_button = QPushButton("Scale Chords")
        self.scale_browser_button = QPushButton("Scale Browser")
        self.inspect_theory_button = QPushButton("Inspect Theory")
        self.gap_suggestion_list = QListWidget()
        self.use_gap_suggestion_button = QPushButton("Use")
        self.inspect_gap_suggestion_button = QPushButton("Inspect")
        self.playback_controls_widget = QWidget()
        self.playback_controls_widget.setLayout(QVBoxLayout())
        self.playback_scroll = QScrollArea()
        self.playback_scroll.setWidgetResizable(True)
        self.playback_scroll.setWidget(self.playback_controls_widget)
        self.timeline = TimelineView()

    def width(self) -> int:
        return self._width


def _wrapped_label(text: str, minimum_height: int) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    if minimum_height:
        label.setMinimumHeight(minimum_height)
    label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
    return label


def test_editor_timeline_width_ignores_long_inspector_text() -> None:
    app = _app()
    window = _EditorWindow(width=1220)
    page = build_editor_page(window)
    page.resize(1220, 650)
    page.show()
    app.processEvents()
    body_layout = page.layout().itemAt(0).layout()
    timeline = body_layout.itemAt(1).widget()
    initial_width = timeline.width()

    window.chord_context.setText(
        "SelectionSuperLongChordNameWithoutBreaksCmaj13SharpElevenAddNineNoFiveSlashGb "
        "(score 100%)"
    )
    app.processEvents()

    assert timeline.width() == initial_width


def test_editor_track_mix_uses_policy_width_for_playback_scroll() -> None:
    _app()
    window = _EditorWindow(width=900)
    page = build_editor_page(window)

    assert window.playback_scroll.minimumWidth() == 220
    assert window.playback_scroll.maximumWidth() == 250
    page.close()


def test_editor_theory_preview_controls_use_two_row_grid() -> None:
    _app()
    window = _EditorWindow(width=1220)
    page = build_editor_page(window)
    side_scroll = page.layout().itemAt(0).layout().itemAt(2).widget()
    side_panel = side_scroll.widget()
    grid = side_panel.layout().itemAt(16).layout()

    assert grid.itemAtPosition(0, 0).widget() is window.preview_scale_button
    assert grid.itemAtPosition(0, 1).widget() is window.preview_scale_pattern
    assert grid.itemAtPosition(1, 0).widget() is window.scale_chords_button
    assert grid.itemAtPosition(1, 1).widget() is window.scale_browser_button


def test_editor_chord_map_controls_use_two_row_grid() -> None:
    _app()
    window = _EditorWindow(width=900)
    page = build_editor_page(window)
    side_scroll = page.layout().itemAt(0).layout().itemAt(2).widget()
    side_panel = side_scroll.widget()
    grid = side_panel.layout().itemAt(9).layout()

    assert grid.itemAtPosition(0, 0).widget() is window.chord_view_mode
    assert grid.itemAtPosition(1, 0).widget() is window.chord_one_octave_button
    assert grid.itemAtPosition(1, 1).widget() is window.note_map_colours


def test_editor_theory_header_uses_wrapped_grid() -> None:
    _app()
    window = _EditorWindow(width=900)
    page = build_editor_page(window)
    side_scroll = page.layout().itemAt(0).layout().itemAt(2).widget()
    side_panel = side_scroll.widget()
    grid = side_panel.layout().itemAt(12).layout()

    assert grid.itemAtPosition(0, 1).widget() is window.show_chromatic_scales
    assert grid.itemAtPosition(1, 0).widget() is window.inspect_theory_button


def test_editor_side_panel_shrinks_to_scroll_viewport() -> None:
    app = _app()
    window = _EditorWindow(width=900)
    page = build_editor_page(window)
    page.resize(900, 520)
    page.show()
    app.processEvents()
    side_scroll = page.layout().itemAt(0).layout().itemAt(2).widget()
    side_panel = side_scroll.widget()

    assert side_panel.minimumWidth() == 0
    assert side_panel.width() <= side_scroll.viewport().width()
