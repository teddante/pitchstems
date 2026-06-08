from __future__ import annotations

from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


def build_pipeline_page(window) -> QWidget:
    output_row = QHBoxLayout()
    output_row.setSpacing(10)
    output_row.addWidget(QLabel("Output"))
    output_row.addWidget(window.output_dir, 1)

    separation_panel = QVBoxLayout()
    separation_panel.setSpacing(8)
    separation_panel.addWidget(section_label("Separation stage"))
    intro = QLabel(
        "PitchStems uses one stem model: BS-RoFormer SW six-stem. "
        "The checkpoint and YAML config come from the native `bs-roformer-infer` registry."
    )
    intro.setWordWrap(True)
    intro.setStyleSheet("color: #4b5563;")
    separation_panel.addWidget(intro)
    separation_panel.addWidget(window.workflow_note)
    separation_card = QGroupBox("BS-RoFormer SW six-stem")
    separation_card_layout = QVBoxLayout()
    separation_card_layout.setSpacing(8)
    separation_card_layout.addWidget(window.model_summary)
    separation_card_layout.addWidget(window.model_facts)
    separation_card_layout.addWidget(window.audio_prep)
    separation_card_layout.addWidget(window.separation_status)
    separation_card.setLayout(separation_card_layout)
    separation_panel.addWidget(separation_card)
    midi_stage_card = QGroupBox("MIDI stage")
    midi_stage_layout = QVBoxLayout()
    midi_stage_layout.setSpacing(8)
    midi_stage_layout.addWidget(window.midi_status)
    midi_stage_card.setLayout(midi_stage_layout)
    separation_panel.addWidget(midi_stage_card)
    separation_panel.addStretch(1)

    selected_panel = QVBoxLayout()
    selected_panel.setSpacing(8)
    selected_panel.addWidget(section_label("Controls"))

    runtime_group = QGroupBox("BS-RoFormer runtime")
    runtime_layout = QVBoxLayout()
    runtime_layout.setSpacing(8)
    runtime_layout.addWidget(window.bs_device)
    runtime_layout.addWidget(window.bs_device_help)
    runtime_group.setLayout(runtime_layout)

    backend_group = QGroupBox("Native backend")
    backend_layout = QVBoxLayout()
    backend_layout.setSpacing(6)
    backend_layout.addWidget(window.model_runtime)
    backend_layout.addWidget(window.model_backend_detail)
    backend_group.setLayout(backend_layout)

    stem_group = QGroupBox("Files to save")
    stem_layout = QVBoxLayout()
    stem_layout.setContentsMargins(10, 8, 10, 8)
    stem_layout.addWidget(window.stem)
    stem_group.setLayout(stem_layout)

    midi_group = QGroupBox("MIDI")
    midi_layout = QVBoxLayout()
    midi_layout.setSpacing(8)
    midi_layout.setContentsMargins(10, 8, 10, 8)
    midi_layout.addWidget(window.generate_midi)
    midi_layout.addLayout(window.midi_stems_layout)
    midi_layout.addWidget(window.midi_help)
    midi_group.setLayout(midi_layout)

    midi_settings_tab = QWidget()
    midi_settings_layout = QVBoxLayout()
    midi_settings_layout.setContentsMargins(8, 8, 8, 8)
    midi_settings_layout.setSpacing(6)
    midi_settings_intro = QLabel(
        "These are Basic Pitch's official `predict_and_save` parameters. "
        "Defaults shown here are Basic Pitch defaults."
    )
    midi_settings_intro.setWordWrap(True)
    midi_settings_intro.setStyleSheet("color: #4b5563;")
    midi_settings_layout.addWidget(midi_settings_intro)
    midi_settings_hint = QLabel(
        "Higher thresholds are stricter and usually create fewer notes. "
        "Frequency limits filter the MIDI note range after prediction."
    )
    midi_settings_hint.setWordWrap(True)
    midi_settings_hint.setStyleSheet("color: #4b5563;")
    midi_settings_layout.addWidget(midi_settings_hint)
    midi_grid = QGridLayout()
    midi_grid.setHorizontalSpacing(10)
    midi_grid.setVerticalSpacing(5)
    grid_control(midi_grid, 0, 0, "Note starts", "default 0.50", window.onset_threshold)
    grid_control(midi_grid, 0, 1, "Sustained notes", "default 0.30", window.frame_threshold)
    grid_control(midi_grid, 1, 0, "Minimum note", "default 127.7 ms", window.minimum_note_length)
    grid_control(midi_grid, 1, 1, "MIDI tempo", "default 120", window.midi_tempo)
    grid_control(midi_grid, 2, 0, "Lowest note", "default off", window.minimum_frequency)
    grid_control(midi_grid, 2, 1, "Highest note", "default off", window.maximum_frequency)
    grid_control(midi_grid, 3, 0, "Check audio rate", "default 44100", window.sonification_samplerate)
    midi_settings_layout.addLayout(midi_grid)

    midi_checks = QGridLayout()
    midi_checks.setHorizontalSpacing(10)
    midi_checks.setVerticalSpacing(3)
    midi_checks.addWidget(window.melodia_trick, 0, 0)
    midi_checks.addWidget(window.multiple_pitch_bends, 0, 1)
    midi_checks.addWidget(window.save_notes, 1, 0)
    midi_checks.addWidget(window.save_model_outputs, 1, 1)
    midi_checks.addWidget(window.sonify_midi, 2, 0)
    midi_settings_layout.addLayout(midi_checks)
    midi_settings_layout.addStretch(1)
    midi_settings_tab.setLayout(midi_settings_layout)

    export_group = QGroupBox("Export")
    export_layout = QVBoxLayout()
    export_layout.setSpacing(8)
    export_layout.setContentsMargins(10, 8, 10, 8)
    export_layout.addWidget(window.create_zip)
    export_layout.addWidget(window.open_when_done)
    export_group.setLayout(export_layout)

    runtime_tab = QWidget()
    runtime_tab_layout = QVBoxLayout()
    runtime_tab_layout.setContentsMargins(8, 8, 8, 8)
    runtime_tab_layout.setSpacing(8)
    runtime_tab_layout.addWidget(runtime_group)
    runtime_tab_layout.addWidget(backend_group)
    runtime_tab_layout.addWidget(export_group)
    runtime_tab_layout.addStretch(1)
    runtime_tab.setLayout(runtime_tab_layout)

    window.processing_tabs.addTab(midi_settings_tab, "Basic Pitch")
    window.processing_tabs.addTab(runtime_tab, "Runtime")

    selected_panel.addWidget(stem_group)
    selected_panel.addWidget(midi_group)
    selected_panel.addWidget(window.processing_tabs, 1)
    selected_panel.addStretch(1)

    main_row = QHBoxLayout()
    main_row.setSpacing(16)
    main_row.addLayout(separation_panel, 3)
    main_row.addLayout(selected_panel, 2)

    action_row = QHBoxLayout()
    action_row.addStretch(1)
    action_row.addWidget(window.cancel_button)
    action_row.addWidget(window.run_midi)
    action_row.addWidget(window.run_full)

    pipeline_layout = QVBoxLayout()
    pipeline_layout.setContentsMargins(12, 12, 12, 12)
    pipeline_layout.setSpacing(10)
    pipeline_layout.addWidget(window.drop_zone)
    pipeline_layout.addLayout(output_row)
    pipeline_layout.addLayout(main_row, 1)
    pipeline_layout.addLayout(action_row)
    pipeline_layout.addWidget(window.log, 1)
    pipeline_page = QWidget()
    pipeline_page.setLayout(pipeline_layout)
    return pipeline_page


def section_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet("font-weight: 700; color: #374151; margin-top: 8px;")
    return label


def grid_control(layout: QGridLayout, row: int, column: int, label: str, default: str, widget: QWidget) -> None:
    stack = QVBoxLayout()
    stack.setSpacing(2)
    title = QLabel(label)
    title.setStyleSheet("font-weight: 600;")
    hint = QLabel(default)
    hint.setStyleSheet("color: #6b7280; font-size: 11px;")
    stack.addWidget(title)
    stack.addWidget(hint)
    stack.addWidget(widget)
    layout.addLayout(stack, row, column)
