from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from pitchstems.gui_helpers import section_label
from pitchstems.gui_layout_policy import EditorLayoutPolicy


def build_editor_page(window) -> QWidget:
    policy = EditorLayoutPolicy(window_width=window.width())
    editor_page = QWidget()
    editor_layout = QVBoxLayout()
    editor_layout.setContentsMargins(12, 12, 12, 12)
    editor_layout.setSpacing(10)

    editor_body = QHBoxLayout()
    editor_body.setSpacing(10)
    editor_side_panel = QWidget()
    editor_side_panel.setMinimumWidth(policy.harmony_panel_min_width)
    editor_side_panel.setMaximumWidth(policy.harmony_panel_width)
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

    chord_action_grid = QGridLayout()
    chord_action_grid.setHorizontalSpacing(6)
    chord_action_grid.setVerticalSpacing(4)
    chord_action_grid.addWidget(window.preview_chord_button, 0, 0)
    chord_action_grid.addWidget(window.use_chord_button, 0, 1)
    chord_action_grid.addWidget(window.reset_note_filter_button, 1, 0)
    chord_action_grid.addWidget(window.inspect_chord_button, 1, 1)
    chord_action_grid.addWidget(window.delete_chord_button, 2, 0, 1, 2)
    editor_side.addLayout(chord_action_grid)
    chord_map_row = QHBoxLayout()
    chord_map_row.setSpacing(6)
    chord_map_row.addWidget(window.chord_view_mode, 1)
    chord_map_row.addWidget(window.chord_one_octave_button)
    chord_map_row.addWidget(window.note_map_colours)
    editor_side.addLayout(chord_map_row)
    editor_side.addWidget(window.chord_note_map_stack)
    editor_side.addWidget(window.chord_list, 1)

    theory_header = QHBoxLayout()
    theory_header.setSpacing(6)
    theory_header.addWidget(section_label("Theory Inspector"))
    theory_header.addWidget(window.show_chromatic_scales)
    theory_header.addWidget(window.inspect_theory_button)
    editor_side.addLayout(theory_header)
    editor_side.addWidget(window.theory_context)
    theory_map_row = QHBoxLayout()
    theory_map_row.setSpacing(6)
    theory_map_row.addWidget(window.theory_view_mode, 1)
    theory_map_row.addWidget(window.theory_one_octave_button)
    editor_side.addLayout(theory_map_row)
    editor_side.addWidget(window.theory_note_map_stack)
    theory_preview_grid = QGridLayout()
    theory_preview_grid.setHorizontalSpacing(6)
    theory_preview_grid.setVerticalSpacing(4)
    theory_preview_grid.addWidget(window.preview_scale_button, 0, 0)
    theory_preview_grid.addWidget(window.preview_scale_pattern, 0, 1)
    theory_preview_grid.addWidget(window.scale_chords_button, 1, 0)
    theory_preview_grid.addWidget(window.scale_browser_button, 1, 1)
    editor_side.addLayout(theory_preview_grid)
    editor_side.addWidget(window.theory_list, 1)

    gap_header = QHBoxLayout()
    gap_header.setSpacing(6)
    gap_header.addWidget(section_label("Gap Suggestions"))
    gap_header.addWidget(window.use_gap_suggestion_button)
    gap_header.addWidget(window.inspect_gap_suggestion_button)
    editor_side.addLayout(gap_header)
    editor_side.addWidget(window.gap_suggestion_list, 1)
    editor_side_panel.setLayout(editor_side)
    editor_side_scroll = QScrollArea()
    editor_side_scroll.setWidgetResizable(True)
    editor_side_scroll.setWidget(editor_side_panel)
    editor_side_scroll.setMinimumWidth(policy.harmony_panel_min_width)
    editor_side_scroll.setMaximumWidth(policy.harmony_panel_width + 18)
    editor_side_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    editor_side_scroll.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

    track_mix_panel = QWidget()
    track_mix_panel.setMinimumWidth(policy.track_panel_min_width)
    track_mix_panel.setMaximumWidth(policy.track_panel_width)
    track_mix_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
    track_mix_layout = QVBoxLayout()
    track_mix_layout.setContentsMargins(0, 0, 0, 0)
    track_mix_layout.setSpacing(0)
    window.playback_scroll.setMinimumWidth(policy.track_panel_min_width)
    window.playback_scroll.setMaximumWidth(policy.track_panel_width)
    track_mix_layout.addWidget(window.playback_scroll, 1)
    track_mix_panel.setLayout(track_mix_layout)

    editor_body.addWidget(track_mix_panel)
    editor_body.addWidget(window.timeline, 1)
    editor_body.addWidget(editor_side_scroll)
    editor_layout.addLayout(editor_body, 1)
    editor_page.setLayout(editor_layout)
    return editor_page
