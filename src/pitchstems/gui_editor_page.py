from __future__ import annotations

from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


def build_editor_page(window) -> QWidget:
    editor_page = QWidget()
    editor_layout = QVBoxLayout()
    editor_layout.setContentsMargins(12, 12, 12, 12)
    editor_layout.setSpacing(10)
    editor_layout.addWidget(window.editor_summary)

    transport_row = QHBoxLayout()
    transport_row.setSpacing(8)
    transport_row.addWidget(window.play_button)
    transport_row.addWidget(window.stop_button)
    transport_row.addWidget(window.fit_song_button)
    transport_row.addWidget(QLabel("Position"))
    transport_row.addWidget(window.editor_position)
    transport_row.addWidget(window.current_chord)
    transport_row.addStretch(1)
    editor_layout.addLayout(transport_row)

    editor_body = QHBoxLayout()
    editor_body.setSpacing(10)
    editor_side_panel = QWidget()
    editor_side_panel.setMinimumWidth(300)
    editor_side_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
    editor_side = QVBoxLayout()
    editor_side.setContentsMargins(0, 0, 0, 0)
    editor_side.setSpacing(8)
    editor_side.addWidget(section_label("Harmony Inspector"))
    editor_side.addWidget(window.notation_spelling)
    editor_side.addWidget(window.chord_context)
    editor_side.addWidget(window.chord_detector_help)

    evidence_floor_row = QHBoxLayout()
    evidence_floor_row.setSpacing(8)
    evidence_floor_row.addWidget(window.min_note_evidence_label)
    evidence_floor_row.addWidget(window.min_note_evidence_slider, 1)
    editor_side.addLayout(evidence_floor_row)
    editor_side.addWidget(section_label("Manual Note Overrides"))
    editor_side.addWidget(window.note_filter_help)
    editor_side.addWidget(window.note_filter_list)

    chord_action_grid = QGridLayout()
    chord_action_grid.setHorizontalSpacing(6)
    chord_action_grid.setVerticalSpacing(4)
    chord_action_grid.addWidget(window.preview_chord_button, 0, 0)
    chord_action_grid.addWidget(window.use_chord_button, 0, 1)
    chord_action_grid.addWidget(window.reset_note_filter_button, 1, 0)
    chord_action_grid.addWidget(window.inspect_chord_button, 1, 1)
    editor_side.addLayout(chord_action_grid)
    editor_side.addWidget(window.piano_chord_view)
    editor_side.addWidget(window.chord_list, 1)

    theory_header = QHBoxLayout()
    theory_header.setSpacing(6)
    theory_header.addWidget(section_label("Theory Inspector"))
    theory_header.addWidget(window.inspect_theory_button)
    editor_side.addLayout(theory_header)
    editor_side.addWidget(window.theory_context)
    editor_side.addWidget(window.theory_list, 1)

    gap_header = QHBoxLayout()
    gap_header.setSpacing(6)
    gap_header.addWidget(section_label("Gap Suggestions"))
    gap_header.addWidget(window.use_gap_suggestion_button)
    gap_header.addWidget(window.inspect_gap_suggestion_button)
    editor_side.addLayout(gap_header)
    editor_side.addWidget(window.gap_suggestion_list, 1)
    editor_side_panel.setLayout(editor_side)

    track_mix_panel = QWidget()
    track_mix_panel.setMinimumWidth(280)
    track_mix_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
    track_mix_layout = QVBoxLayout()
    track_mix_layout.setContentsMargins(0, 0, 0, 0)
    track_mix_layout.setSpacing(0)
    track_mix_layout.addWidget(window.playback_scroll, 1)
    track_mix_panel.setLayout(track_mix_layout)

    editor_body.addWidget(editor_side_panel)
    editor_body.addWidget(track_mix_panel)
    editor_body.addWidget(window.timeline, 1)
    editor_layout.addLayout(editor_body, 1)
    editor_page.setLayout(editor_layout)
    return editor_page


def section_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet("font-weight: 700; color: #374151; margin-top: 8px;")
    return label
