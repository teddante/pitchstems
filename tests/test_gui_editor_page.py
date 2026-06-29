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
    QVBoxLayout,
    QWidget,
)

from pitchstems.gui_editor_page import build_editor_page
from pitchstems.gui_timeline import TimelineView
from pitchstems.gui_widgets import PianoChordWidget


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
        self.reset_note_filter_button = QPushButton("Reset Evidence")
        self.inspect_chord_button = QPushButton("Inspect")
        self.piano_chord_view = PianoChordWidget()
        self.preview_bass_note = QComboBox()
        self.preview_top_note = QComboBox()
        self.chord_list = QListWidget()
        self.theory_context = _wrapped_label("Theory: -", 54)
        self.theory_list = QListWidget()
        self.show_chromatic_scales = QCheckBox("Chromatic")
        self.preview_scale_button = QPushButton("Play Scale")
        self.preview_scale_pattern = QComboBox()
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
