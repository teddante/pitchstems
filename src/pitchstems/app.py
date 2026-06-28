from __future__ import annotations

import os
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from pitchstems.app_logging import app_logger, setup_app_logging
from pitchstems.chord_preview import chord_preview_pitches
from pitchstems.editor_project import (
    ChordRegion,
    ChordScoringOptions,
    EditorProject,
    NoteEvent,
    chord_bass_name_for_label,
    chord_tones_for_label,
    display_chord_label,
    midi_note_name,
)
from pitchstems.editor_playback import review_playback_loop_range
from pitchstems.editor_loader import EditorLoadResult
from pitchstems.gui_editor_model import EMPTY_EDITOR_SUMMARY
from pitchstems.midi_preview import render_note_preview
from pitchstems.notation import pitch_class_for_name, pitch_class_name
from pitchstems.pipeline_models import PipelineResult, StemResult
from pitchstems.harmony_inspector import (
    chord_analysis_track_names as inspector_chord_analysis_track_names,
    resolve_notation_preference,
)
from pitchstems import harmony_panel
from pitchstems import gui_editor_actions
from pitchstems import gui_harmony_dialogs
from pitchstems import gui_harmony_flow
from pitchstems import gui_export
from pitchstems import gui_pipeline_state
from pitchstems import gui_processing
from pitchstems import gui_editor_load
from pitchstems import gui_editor_state
from pitchstems import gui_project_flow
from pitchstems import gui_shutdown
from pitchstems import gui_transport_flow
from pitchstems.gui_jobs import EditorLoadJobState, MidiPreviewJobState, WorkerJobState
from pitchstems.gui_theme import pitchstems_stylesheet
from pitchstems.gui_track_controls import rebuild_track_controls, sync_track_control_panel as sync_track_controls
from pitchstems.theory import ChordGapAnalysis, TheoryAnalysis
from pitchstems.time_format import format_time
from pitchstems.transcription import midi_option_spec

@dataclass(frozen=True)
class HarmonyContext:
    mode: str
    sampled_tracks: tuple[str, ...]


def main() -> int:
    log_path = setup_app_logging()
    logger = app_logger()
    try:
        from PySide6.QtCore import QSettings, QTimer, Qt, QUrl
        from PySide6.QtGui import QAction, QKeySequence, QShortcut
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        from PySide6.QtWidgets import (
            QApplication,
            QButtonGroup,
            QCheckBox,
            QComboBox,
            QDoubleSpinBox,
            QFrame,
            QGridLayout,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QListWidget,
            QListWidgetItem,
            QMainWindow,
            QProgressBar,
            QPushButton,
            QScrollArea,
            QSizePolicy,
            QSlider,
            QSpinBox,
            QTabWidget,
            QTextEdit,
            QVBoxLayout,
            QWidget,
        )
    except ImportError:
        print("PySide6 is not installed. Install with `pip install -e .[gui]`.")
        return 1

    from pitchstems.gui_widgets import (
        DropZone,
        NoWheelComboBox,
        NoWheelDoubleSpinBox,
        NoWheelSpinBox,
        PianoChordWidget,
    )
    from pitchstems.gui_import_clip import ImportClipPicker, clip_status_text, import_preview_range
    from pitchstems.gui_editor_page import build_editor_page
    from pitchstems.gui_pipeline_page import build_pipeline_page
    from pitchstems.gui_timeline import TimelineView
    from pitchstems.gui_transport import (
        TransportController,
        find_existing_midi_previews,
        loop_playback_start,
        reset_player_source,
        safe_qt_multimedia_call,
        start_player_source,
    )

    class MainWindow(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("PitchStems")
            self.resize(1220, 780)
            self.log_path = log_path
            self.logger = logger
            self.messages: queue.Queue[object] = queue.Queue()
            self.worker: threading.Thread | None = None
            self.worker_jobs = WorkerJobState()
            self.editor_load_jobs = EditorLoadJobState()
            self.midi_preview_jobs = MidiPreviewJobState()
            self.close_after_worker = False
            self.latest_output_dir: Path | None = None
            self.current_result: PipelineResult | None = None
            self.current_stems: list[StemResult] = []
            self.current_input_stem: str | None = None
            self.settings = QSettings("PitchStems", "PitchStems")
            self.recent_projects_menu = None
            self.base_editor_project: EditorProject | None = None
            self.editor_project: EditorProject | None = None
            self.track_analysis_checks: dict[str, QCheckBox] = {}
            self.track_audio_checks: dict[str, QCheckBox] = {}
            self.track_audio_sliders: dict[str, QSlider] = {}
            self.track_midi_checks: dict[str, QCheckBox] = {}
            self.track_midi_sliders: dict[str, QSlider] = {}
            self.transport = TransportController(
                parent=self,
                logger=self.logger,
                track_audio_checks=self.track_audio_checks,
                track_audio_sliders=self.track_audio_sliders,
                track_midi_checks=self.track_midi_checks,
                track_midi_sliders=self.track_midi_sliders,
            )
            self.rendering_midi_previews: set[str] = set()
            self.activity_depth = 0
            self.manual_chords: list[ChordRegion] = []
            self.removed_chord_ranges: list[tuple[float, float]] = []
            self.chord_note_overrides: dict[int, str] = {}
            self.chord_note_filter_context = None
            self.current_chord_base_weights: dict[int, float] = {}
            self.current_harmony_context: HarmonyContext | None = None
            self.harmony_refresh_gate = gui_harmony_flow.HarmonyRefreshGate()
            self.current_theory_analysis: TheoryAnalysis | None = None
            self.current_chord_gap_analysis: ChordGapAnalysis | None = None
            self.updating_chord_note_filter = False

            self.drop_zone = DropZone()
            self.drop_zone.on_path_changed = self.reset_stage_state
            self.import_clip_player = QMediaPlayer(self)
            self.import_clip_audio = QAudioOutput(self)
            self.import_clip_player.setAudioOutput(self.import_clip_audio)
            self.import_clip_audio.setVolume(0.8)
            self.import_clip_timer = QTimer(self)
            self.import_clip_timer.setInterval(80)
            self.import_clip_timer.timeout.connect(self.poll_import_clip_preview)
            self.import_clip_preview_end_seconds: float | None = None
            self.import_clip_picker = ImportClipPicker()
            self.import_clip_status = QLabel("Whole file")
            self.import_clip_status.setWordWrap(True)
            self.import_clip_status.setStyleSheet("color: #4b5563;")
            self.import_clip_play = QPushButton("Play")
            self.import_clip_play.setEnabled(False)
            self.import_clip_play.clicked.connect(self.play_import_clip_preview)
            self.import_clip_stop = QPushButton("Stop")
            self.import_clip_stop.setEnabled(False)
            self.import_clip_stop.clicked.connect(self.stop_import_clip_preview)
            self.import_clip_clear = QPushButton("Clear")
            self.import_clip_clear.setEnabled(False)
            self.import_clip_clear.clicked.connect(self.import_clip_picker.clear_selection)
            self.import_clip_picker.on_range_changed = self.update_import_clip_status
            self.output_dir = QLineEdit(str(Path.home() / "PitchStems Projects"))
            self.output_dir.setReadOnly(True)

            self.separation_status = QLabel("Not run yet.")
            self.separation_status.setWordWrap(True)
            self.separation_status.setStyleSheet("color: #4b5563;")
            self.midi_status = QLabel("Run the full pipeline first, then MIDI can be rerun without separating again.")
            self.midi_status.setWordWrap(True)
            self.midi_status.setStyleSheet("color: #4b5563;")
            self.workflow_note = QLabel("Use Run separation + MIDI after changing separation/output settings. Use Rerun MIDI only after changing Basic Pitch settings or MIDI stem ticks.")
            self.workflow_note.setWordWrap(True)
            self.workflow_note.setStyleSheet("color: #4b5563;")

            self.model_summary = QLabel()
            self.model_summary.setWordWrap(True)
            self.model_facts = QLabel()
            self.model_facts.setWordWrap(True)
            self.model_facts.setStyleSheet("color: #374151;")
            self.audio_prep = QLabel(
                "Import prep: FFmpeg converts the dropped file to stereo 44.1 kHz PCM WAV for BS-RoFormer. "
                "Basic Pitch then loads each separated WAV and resamples internally to mono 22.05 kHz."
            )
            self.audio_prep.setWordWrap(True)
            self.audio_prep.setStyleSheet("color: #4b5563;")
            self.model_runtime = QLabel()
            self.model_runtime.setWordWrap(True)
            self.model_backend_detail = QLabel()
            self.model_backend_detail.setWordWrap(True)
            self.model_backend_detail.setStyleSheet("color: #4b5563;")
            self.processing_tabs = QTabWidget()
            self.processing_tabs.setDocumentMode(True)

            self.bs_device = NoWheelComboBox()
            self.bs_device.addItem("Auto: CUDA if available", None)
            self.bs_device.addItem("Force CUDA GPU", "cuda:0")
            self.bs_device.addItem("Force CPU", "cpu")
            self.bs_device_help = QLabel("Official BS-RoFormer device setting. Model quality settings come from the downloaded YAML config.")
            self.bs_device_help.setWordWrap(True)
            self.bs_device_help.setStyleSheet("color: #4b5563;")

            self.stem = NoWheelComboBox()
            self.stem.currentIndexChanged.connect(self.refresh_midi_stem_checks)
            self.generate_midi = QCheckBox("Generate MIDI with Basic Pitch")
            self.generate_midi.setChecked(True)
            self.midi_stem_checks: dict[str, QCheckBox] = {}
            self.midi_stems_layout = QGridLayout()
            self.midi_stems_layout.setHorizontalSpacing(12)
            self.midi_stems_layout.setVerticalSpacing(4)
            self.midi_help = QLabel("Tick the saved stems that Basic Pitch should analyse. Drums are off by default because Basic Pitch is for pitched notes.")
            self.midi_help.setWordWrap(True)
            self.midi_help.setStyleSheet("color: #4b5563;")
            onset_threshold = midi_option_spec("onset_threshold")
            self.onset_threshold = _double_spin(
                0.0,
                1.0,
                onset_threshold.default_value(),
                0.05,
                2,
            )
            self.onset_threshold.setToolTip(onset_threshold.gui_tooltip())
            frame_threshold = midi_option_spec("frame_threshold")
            self.frame_threshold = _double_spin(
                0.0,
                1.0,
                frame_threshold.default_value(),
                0.05,
                2,
            )
            self.frame_threshold.setToolTip(frame_threshold.gui_tooltip())
            minimum_note_length = midi_option_spec("minimum_note_length")
            self.minimum_note_length = _double_spin(
                0.0,
                1000.0,
                minimum_note_length.default_value(),
                10.0,
                1,
            )
            self.minimum_note_length.setToolTip(minimum_note_length.gui_tooltip())
            self.minimum_frequency = _frequency_spin("No lower limit")
            self.minimum_frequency.setToolTip(midi_option_spec("minimum_frequency").gui_tooltip())
            self.maximum_frequency = _frequency_spin("No upper limit")
            self.maximum_frequency.setToolTip(midi_option_spec("maximum_frequency").gui_tooltip())
            midi_tempo = midi_option_spec("midi_tempo")
            self.midi_tempo = _double_spin(
                20.0,
                300.0,
                midi_tempo.default_value(),
                1.0,
                1,
            )
            self.midi_tempo.setToolTip(midi_tempo.gui_tooltip())
            melodia_trick = midi_option_spec("melodia_trick")
            self.melodia_trick = QCheckBox(melodia_trick.checkbox_text())
            self.melodia_trick.setChecked(melodia_trick.default_value())
            self.melodia_trick.setToolTip(melodia_trick.gui_tooltip())
            multiple_pitch_bends = midi_option_spec("multiple_pitch_bends")
            self.multiple_pitch_bends = QCheckBox(multiple_pitch_bends.checkbox_text())
            self.multiple_pitch_bends.setChecked(multiple_pitch_bends.default_value())
            self.multiple_pitch_bends.setToolTip(multiple_pitch_bends.gui_tooltip())
            save_notes = midi_option_spec("save_notes")
            self.save_notes = QCheckBox(save_notes.checkbox_text())
            self.save_notes.setChecked(save_notes.default_value())
            save_model_outputs = midi_option_spec("save_model_outputs")
            self.save_model_outputs = QCheckBox(save_model_outputs.checkbox_text())
            self.save_model_outputs.setChecked(save_model_outputs.default_value())
            self.save_model_outputs.setToolTip(save_model_outputs.gui_tooltip())
            sonify_midi = midi_option_spec("sonify_midi")
            self.sonify_midi = QCheckBox(sonify_midi.checkbox_text())
            self.sonify_midi.setChecked(sonify_midi.default_value())
            self.sonification_samplerate = NoWheelSpinBox()
            self.sonification_samplerate.setRange(8000, 192000)
            self.sonification_samplerate.setSingleStep(1000)
            self.sonification_samplerate.setValue(
                midi_option_spec("sonification_samplerate").default_value()
            )
            self.sonification_samplerate.setEnabled(False)

            self.open_when_done = QCheckBox("Open output folder when finished")
            self.open_when_done.setChecked(False)
            self.export_button = QPushButton("Export...")
            self.export_button.setEnabled(False)
            self.export_action: QAction | None = None

            self.run_full = QPushButton("Run separation + MIDI")
            self.run_full.setObjectName("primaryAction")
            self.run_midi = QPushButton("Rerun MIDI only")
            self.run_midi.setEnabled(False)
            self.cancel_button = QPushButton("Cancel")
            self.cancel_button.setEnabled(False)
            self.log = QTextEdit()
            self.log.setReadOnly(True)
            self.editor_summary = QLabel(EMPTY_EDITOR_SUMMARY)
            self.editor_summary.setWordWrap(True)
            self.editor_summary.setStyleSheet("color: #4b5563;")
            self.editor_position = QLabel("00:00.000")
            self.editor_position.setMinimumWidth(86)
            self.current_chord = QLabel("Harmony: -")
            self.current_chord.setMinimumWidth(220)
            self.current_chord.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            self.current_chord.setStyleSheet("font-weight: 700; color: #4c1d95;")
            self.chord_context = QLabel("Sample: -")
            self.chord_context.setWordWrap(True)
            self.chord_context.setMinimumHeight(64)
            self.chord_context.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            self.chord_context.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            self.chord_context.setStyleSheet("color: #475569;")
            self.note_filter_list = QListWidget()
            self.note_filter_list.setMinimumHeight(96)
            self.note_filter_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            self.note_filter_list.setAlternatingRowColors(True)
            self.note_filter_list.setToolTip("Optional corrections: Auto uses energy evidence, Exclude rejects chord names containing a note, Force requires chord names containing a note.")
            self.note_filter_help = QLabel(
                "Auto uses the MIDI energy evidence. Use Exclude or Force only when you want to correct the detector."
            )
            self.note_filter_help.setWordWrap(True)
            self.note_filter_help.setStyleSheet("color: #64748b;")
            self.reset_note_filter_button = QPushButton("Reset Evidence")
            self.reset_note_filter_button.setToolTip("Clear manual include/exclude note choices for the current chord analysis.")
            self.chord_detector_help = QLabel(
                "Harmony comes from the selected Chord tracks: MIDI note energy feeds chord detection, then the chord track feeds key, scale, mode, and gap suggestions."
            )
            self.chord_detector_help.setWordWrap(True)
            self.chord_detector_help.setStyleSheet("color: #64748b;")
            self.min_note_evidence_label = QLabel("Min note evidence: 0%")
            self.min_note_evidence_label.setStyleSheet("color: #334155;")
            self.min_note_evidence_slider = QSlider(Qt.Horizontal)
            self.min_note_evidence_slider.setRange(0, 100)
            self.min_note_evidence_slider.setValue(0)
            self.min_note_evidence_slider.setToolTip(
                "Ignore note names below this normalized evidence level when naming chords. Raw evidence still appears in Inspect."
            )
            self.notation_spelling = NoWheelComboBox()
            self.notation_spelling.addItem("Notation: Auto", "auto")
            self.notation_spelling.addItem("Notation: Sharps", "sharp")
            self.notation_spelling.addItem("Notation: Flats", "flat")
            self.notation_spelling.setToolTip(
                "Controls enharmonic spelling for displayed notes and chords. Auto follows the current key/chord context where possible."
            )
            self.timeline = TimelineView()
            self.timeline.set_note_name_formatter(self.display_note_name)
            self.timeline.on_position_changed = self.set_editor_position_seconds
            self.timeline.on_selection_changed = self.set_editor_selection
            self.timeline.on_chord_edited = self.edit_timeline_chord
            self.timeline.on_chord_deleted = self.delete_timeline_chord
            self.timeline.on_chord_selected = self.show_timeline_chord_status
            self.timeline.on_redraw_started = self.begin_timeline_redraw
            self.timeline.on_redraw_finished = self.finish_timeline_redraw
            self.playback_controls = QVBoxLayout()
            self.playback_controls.setSpacing(0)
            self.playback_controls.setContentsMargins(0, 0, 0, 0)
            self.playback_controls_widget = QWidget()
            self.playback_controls_widget.setLayout(self.playback_controls)
            self.playback_scroll = QScrollArea()
            self.playback_scroll.setWidgetResizable(True)
            self.playback_scroll.setWidget(self.playback_controls_widget)
            self.playback_scroll.setMinimumWidth(270)
            self.playback_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.playback_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.playback_scroll.setStyleSheet("QScrollArea { border: 1px solid #e2e8f0; background: #f8fafc; }")
            self.track_visibility_checks: dict[str, QCheckBox] = {}
            self.track_analysis_checks: dict[str, QCheckBox] = {}
            self.track_control_panels: dict[str, QWidget] = {}
            self.track_control_detail_rows: dict[str, tuple[QWidget, QWidget, QWidget]] = {}
            self.track_control_top_spacer: QWidget | None = None
            self.track_control_bottom_spacer: QWidget | None = None
            self.hidden_track_status: QLabel | None = None
            self.track_note_counts: dict[str, int] = {}
            self.editor_track_visibility: dict[str, bool] = {}
            self.chord_list = QListWidget()
            self.chord_list.setMinimumHeight(130)
            self.chord_list.setAlternatingRowColors(True)
            self.theory_context = QLabel("Theory: -")
            self.theory_context.setWordWrap(True)
            self.theory_context.setMinimumHeight(54)
            self.theory_context.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            self.theory_context.setStyleSheet("color: #475569;")
            self.theory_list = QListWidget()
            self.theory_list.setMinimumHeight(120)
            self.theory_list.setAlternatingRowColors(True)
            self.inspect_theory_button = QPushButton("Inspect Theory")
            self.inspect_theory_button.setEnabled(False)
            self.inspect_theory_button.setToolTip(
                "Open a detailed report of the current scale, key, mode, and progression evidence."
            )
            self.gap_suggestion_list = QListWidget()
            self.gap_suggestion_list.setMinimumHeight(105)
            self.gap_suggestion_list.setAlternatingRowColors(True)
            self.use_gap_suggestion_button = QPushButton("Use")
            self.use_gap_suggestion_button.setEnabled(False)
            self.inspect_gap_suggestion_button = QPushButton("Inspect")
            self.inspect_gap_suggestion_button.setEnabled(False)
            self.piano_chord_view = PianoChordWidget()
            self.preview_chord_button = QPushButton("Play Chord")
            self.use_chord_button = QPushButton("Use for Selection")
            self.delete_chord_button = QPushButton("Delete Chord")
            self.inspect_chord_button = QPushButton("Inspect")
            self.preview_chord_button.setEnabled(False)
            self.use_chord_button.setEnabled(False)
            self.delete_chord_button.setEnabled(False)
            self.inspect_chord_button.setEnabled(False)
            self.inspect_chord_button.setToolTip("Open a detailed report of the current harmony inputs, note weights, constraints, and chord candidate scoring.")
            self.chord_preview_player = QMediaPlayer(self)
            self.chord_preview_output = QAudioOutput(self)
            self.chord_preview_output.setVolume(0.85)
            self.chord_preview_player.setAudioOutput(self.chord_preview_output)
            self.play_button = QPushButton("Play")
            self.play_button.setObjectName("transportPrimary")
            self.play_review_button = QPushButton("Play Review")
            self.play_review_button.setEnabled(False)
            self.previous_chord_button = QPushButton("Prev Chord")
            self.previous_chord_button.setEnabled(False)
            self.next_chord_button = QPushButton("Next Chord")
            self.next_chord_button.setEnabled(False)
            self.stop_button = QPushButton("Stop")
            self.stop_button.setObjectName("transportIcon")
            self.stop_button.setEnabled(False)
            self.fit_song_button = QPushButton("Fit Song")
            self.fit_song_button.setEnabled(False)
            self.fit_review_button = QPushButton("Fit Review")
            self.fit_review_button.setEnabled(False)

            pipeline_page = build_pipeline_page(self)
            editor_page = build_editor_page(self)

            self.main_tabs = QTabWidget()
            self.main_tabs.addTab(pipeline_page, "Pipeline")
            self.main_tabs.addTab(editor_page, "Editor")
            self.main_tabs.tabBar().hide()
            self.main_tabs.currentChanged.connect(self.sync_workspace_nav)

            self.workspace_nav_buttons: dict[str, QPushButton] = {}
            self.setCentralWidget(self.build_workspace_shell())
            self.create_menus()
            self.activity_label = QLabel("Ready")
            self.activity_label.setMinimumWidth(180)
            self.activity_bar = QProgressBar()
            self.activity_bar.setRange(0, 1)
            self.activity_bar.setValue(1)
            self.activity_bar.setMinimumWidth(120)
            self.activity_bar.setTextVisible(False)
            self.statusBar().addPermanentWidget(self.activity_label)
            self.statusBar().addPermanentWidget(self.activity_bar)
            self.statusBar().showMessage(
                "Timeline: Space plays/pauses; Alt+Left/Right steps chords; drag chord lane or Shift+drag to select chord-analysis range; Ctrl+drag adds another range; Esc clears selection; wheel scrolls, Ctrl+wheel zooms."
            )
            self.space_playback_shortcut = QShortcut(QKeySequence("Space"), self)
            self.space_playback_shortcut.setContext(Qt.ApplicationShortcut)
            self.space_playback_shortcut.activated.connect(self.toggle_playback_from_shortcut)
            self.clear_selection_shortcut = QShortcut(QKeySequence("Esc"), self)
            self.clear_selection_shortcut.setContext(Qt.ApplicationShortcut)
            self.clear_selection_shortcut.activated.connect(self.clear_editor_selection)

            self.run_full.clicked.connect(self.start_full_processing)
            self.run_midi.clicked.connect(self.start_midi_processing)
            self.export_button.clicked.connect(lambda: gui_export.export_selected_files(self))
            self.cancel_button.clicked.connect(self.cancel_processing)
            self.play_button.clicked.connect(self.toggle_playback)
            self.play_review_button.clicked.connect(
                lambda: gui_editor_actions.play_editor_review_target(self)
            )
            self.previous_chord_button.clicked.connect(lambda: self.select_review_chord(-1))
            self.next_chord_button.clicked.connect(lambda: self.select_review_chord(1))
            self.stop_button.clicked.connect(self.stop_transport)
            self.fit_song_button.clicked.connect(
                lambda: gui_editor_actions.fit_editor_song_to_view(self)
            )
            self.fit_review_button.clicked.connect(
                lambda: gui_editor_actions.fit_editor_review_to_view(self)
            )
            self.preview_chord_button.clicked.connect(self.preview_selected_chord)
            self.use_chord_button.clicked.connect(self.assign_selected_chord_to_selection)
            self.delete_chord_button.clicked.connect(self.delete_selected_chord)
            self.reset_note_filter_button.clicked.connect(self.reset_chord_note_filter)
            self.inspect_chord_button.clicked.connect(self.inspect_current_chord_analysis)
            self.inspect_theory_button.clicked.connect(self.inspect_current_theory_analysis)
            self.use_gap_suggestion_button.clicked.connect(self.use_selected_gap_suggestion)
            self.inspect_gap_suggestion_button.clicked.connect(self.inspect_current_gap_suggestions)
            self.gap_suggestion_list.currentItemChanged.connect(
                lambda *_args: self.refresh_gap_suggestion_actions()
            )
            self.notation_spelling.currentIndexChanged.connect(self.handle_notation_spelling_changed)
            self.note_filter_list.itemChanged.connect(self.handle_chord_note_filter_changed)
            self.min_note_evidence_slider.valueChanged.connect(self.handle_min_note_evidence_changed)
            self.chord_list.itemDoubleClicked.connect(self.preview_chord_item)
            self.chord_list.currentItemChanged.connect(self.handle_chord_selection_changed)
            self.timeline.verticalScrollBar().valueChanged.connect(self.sync_track_control_scroll)
            self.playback_scroll.verticalScrollBar().valueChanged.connect(self.sync_timeline_scroll)
            self.bs_device.currentIndexChanged.connect(self.refresh_model_details)
            self.generate_midi.toggled.connect(self.refresh_midi_stem_checks)
            self.sonify_midi.toggled.connect(self.sonification_samplerate.setEnabled)

            self.refresh_model_details()
            self.drop_zone.setFocus()

            self.timer = QTimer(self)
            self.timer.timeout.connect(self.flush_messages)
            self.timer.start(100)

            self.transport_timer = QTimer(self)
            self.transport_timer.timeout.connect(self.update_transport_position)
            self.editor_save_timer = QTimer(self)
            self.editor_save_timer.setSingleShot(True)
            self.editor_save_timer.timeout.connect(self.save_editor_state)

        def closeEvent(self, event) -> None:
            if not gui_shutdown.request_window_close(self):
                event.ignore()
                return
            self.save_editor_state()
            super().closeEvent(event)

        def begin_activity(self, message: str, busy: bool = True) -> None:
            self.activity_depth += 1
            self.activity_label.setText(message)
            self.statusBar().showMessage(message)
            if busy:
                self.activity_bar.setRange(0, 0)
            else:
                self.activity_bar.setRange(0, 1)
                self.activity_bar.setValue(0)
            QApplication.processEvents()

        def end_activity(self, message: str = "Ready") -> None:
            self.activity_depth = max(0, self.activity_depth - 1)
            if self.activity_depth:
                return
            self.activity_label.setText(message)
            self.activity_bar.setRange(0, 1)
            self.activity_bar.setValue(1)
            self.statusBar().showMessage(message, 4000)
            QApplication.processEvents()

        def reset_activity(self, message: str = "Ready") -> None:
            self.activity_depth = 0
            self.activity_label.setText(message)
            self.activity_bar.setRange(0, 1)
            self.activity_bar.setValue(1)
            self.statusBar().showMessage(message, 4000)

        def begin_timeline_redraw(self) -> None:
            if self.activity_depth:
                return
            self.activity_label.setText("Redrawing timeline...")
            self.activity_bar.setRange(0, 0)

        def finish_timeline_redraw(self) -> None:
            self.sync_track_control_panel()
            self.sync_track_control_scroll(self.timeline.verticalScrollBar().value())
            if self.activity_depth:
                return
            self.activity_label.setText("Ready")
            self.activity_bar.setRange(0, 1)
            self.activity_bar.setValue(1)
            message = self.timeline.last_redraw_stats or "Timeline ready"
            self.statusBar().showMessage(message, 2500)

        def set_activity_message(self, message: str) -> None:
            self.activity_label.setText(message)
            self.statusBar().showMessage(message)
            QApplication.processEvents()

        def build_workspace_shell(self) -> QWidget:
            root = QWidget()
            root.setObjectName("appShell")
            root_layout = QHBoxLayout()
            root_layout.setContentsMargins(0, 0, 0, 0)
            root_layout.setSpacing(0)

            rail = QFrame()
            rail.setObjectName("sideRail")
            rail.setFixedWidth(90)
            rail_layout = QVBoxLayout()
            rail_layout.setContentsMargins(8, 10, 6, 10)
            rail_layout.setSpacing(6)

            brand = QLabel("PitchStems")
            brand.setObjectName("brandTitle")
            brand.setAlignment(Qt.AlignCenter)
            rail_layout.addWidget(brand)
            rail_layout.addSpacing(14)

            self.workspace_nav_group = QButtonGroup(self)
            self.workspace_nav_group.setExclusive(True)
            for label, tab_index in (
                ("Pipeline", 0),
                ("Editor", 1),
            ):
                button = QPushButton(label)
                button.setObjectName("navButton")
                button.setCheckable(True)
                button.clicked.connect(lambda _checked=False, index=tab_index: self.main_tabs.setCurrentIndex(index))
                self.workspace_nav_group.addButton(button)
                rail_layout.addWidget(button)
                self.workspace_nav_buttons[label] = button
            rail_layout.addStretch(1)

            help_button = QPushButton("Help")
            help_button.setObjectName("navButton")
            help_button.clicked.connect(self.show_timeline_controls)
            rail_layout.addWidget(help_button)
            rail.setLayout(rail_layout)

            workspace = QWidget()
            workspace_layout = QVBoxLayout()
            workspace_layout.setContentsMargins(12, 10, 12, 0)
            workspace_layout.setSpacing(10)
            workspace_layout.addWidget(self.build_top_bar())
            workspace_layout.addWidget(self.build_project_strip())
            workspace_layout.addWidget(self.main_tabs, 1)
            workspace.setLayout(workspace_layout)

            root_layout.addWidget(rail)
            root_layout.addWidget(workspace, 1)
            root.setLayout(root_layout)
            self.sync_workspace_nav(self.main_tabs.currentIndex())
            return root

        def build_top_bar(self) -> QWidget:
            bar = QFrame()
            bar.setObjectName("topBar")
            layout = QHBoxLayout()
            layout.setContentsMargins(12, 8, 12, 8)
            layout.setSpacing(8)
            layout.addWidget(self.play_button)
            layout.addWidget(self.play_review_button)
            layout.addWidget(self.previous_chord_button)
            layout.addWidget(self.next_chord_button)
            layout.addWidget(self.stop_button)
            layout.addWidget(self.fit_song_button)
            layout.addWidget(self.fit_review_button)
            position_label = QLabel("Position")
            position_label.setObjectName("eyebrow")
            layout.addWidget(position_label)
            layout.addWidget(self.editor_position)
            layout.addWidget(self.current_chord, 1)
            layout.addStretch(1)
            layout.addWidget(self.export_button)
            layout.addWidget(self.cancel_button)
            layout.addWidget(self.run_midi)
            layout.addWidget(self.run_full)
            bar.setLayout(layout)
            return bar

        def build_project_strip(self) -> QWidget:
            strip = QFrame()
            strip.setObjectName("projectStrip")
            layout = QHBoxLayout()
            layout.setContentsMargins(12, 8, 12, 8)
            layout.setSpacing(10)
            project_label = QLabel("Project")
            project_label.setObjectName("eyebrow")
            layout.addWidget(project_label)
            layout.addWidget(self.editor_summary, 1)
            status_label = QLabel("Status")
            status_label.setObjectName("eyebrow")
            layout.addWidget(status_label)
            layout.addWidget(self.separation_status)
            strip.setLayout(layout)
            return strip

        def sync_workspace_nav(self, index: int) -> None:
            target = "Pipeline" if index == 0 else "Editor"
            button = self.workspace_nav_buttons.get(target)
            if button is not None:
                button.setChecked(True)

        def create_menus(self) -> None:
            file_menu = self.menuBar().addMenu("&File")
            self._add_action(file_menu, "&Open Audio...", "Ctrl+O", lambda: gui_project_flow.pick_audio(self))
            self._add_action(file_menu, "Open &Project...", "Ctrl+Shift+O", lambda: gui_project_flow.pick_project(self))
            self.recent_projects_menu = file_menu.addMenu("Open &Recent")
            gui_project_flow.refresh_recent_projects_menu(self)
            file_menu.addSeparator()
            self._add_action(file_menu, "&Save Project", "Ctrl+S", lambda: gui_project_flow.save_project_now(self))
            self.export_action = self._add_action(
                file_menu,
                "Export Selected Files...",
                None,
                lambda: gui_export.export_selected_files(self),
            )
            self.export_action.setEnabled(False)
            self._add_action(file_menu, "Choose Output &Folder...", None, lambda: gui_project_flow.pick_output_dir(self))
            self._add_action(file_menu, "Open Output Folder", "Ctrl+E", self.open_latest_output)
            self._add_action(file_menu, "Open Logs Folder", None, self.open_logs_folder)
            file_menu.addSeparator()
            self._add_action(file_menu, "E&xit", "Alt+F4", self.close)

            run_menu = self.menuBar().addMenu("&Run")
            self._add_action(run_menu, "Run Separation + MIDI", "F5", self.start_full_processing)
            self._add_action(run_menu, "Rerun MIDI Only", "Shift+F5", self.start_midi_processing)
            self._add_action(run_menu, "Cancel Processing", None, self.cancel_processing)

            view_menu = self.menuBar().addMenu("&View")
            self._add_action(view_menu, "Pipeline", "Ctrl+1", lambda: self.main_tabs.setCurrentIndex(0))
            self._add_action(view_menu, "Editor", "Ctrl+2", lambda: self.main_tabs.setCurrentIndex(1))
            view_menu.addSeparator()
            zoom_time_in = self._add_action(
                view_menu,
                "Zoom Time In",
                None,
                lambda: self.timeline.zoom_horizontal(1.18),
            )
            zoom_time_in.setShortcuts([QKeySequence("Ctrl++"), QKeySequence("Ctrl+=")])
            self._add_action(view_menu, "Zoom Time Out", "Ctrl+-", lambda: self.timeline.zoom_horizontal(1 / 1.18))
            self._add_action(
                view_menu,
                "Zoom Pitch In",
                "Ctrl+Shift++",
                lambda: self.timeline.zoom_vertical(1.18),
            )
            self._add_action(
                view_menu,
                "Zoom Pitch Out",
                "Ctrl+Shift+-",
                lambda: self.timeline.zoom_vertical(1 / 1.18),
            )
            self._add_action(view_menu, "Reset Timeline Zoom", "Ctrl+0", self.timeline.reset_zoom)
            self._add_action(
                view_menu,
                "Fit Whole Song",
                "Ctrl+Alt+0",
                lambda: gui_editor_actions.fit_editor_song_to_view(self),
            )
            self._add_action(
                view_menu,
                "Fit Review Target",
                "Ctrl+Alt+F",
                lambda: gui_editor_actions.fit_editor_review_to_view(self),
            )
            view_menu.addSeparator()
            self._add_action(view_menu, "Previous Chord", "Alt+Left", lambda: self.select_review_chord(-1))
            self._add_action(view_menu, "Next Chord", "Alt+Right", lambda: self.select_review_chord(1))

            help_menu = self.menuBar().addMenu("&Help")
            self._add_action(help_menu, "Show Timeline Controls", None, self.show_timeline_controls)

        def _add_action(self, menu, text: str, shortcut: str | None, callback) -> QAction:
            action = QAction(text, self)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(callback)
            menu.addAction(action)
            return action

        # Thin slot adapters keep Qt connections and cross-module callbacks on MainWindow
        # while the behavior lives in focused gui_* modules.
        def show_timeline_controls(self) -> None:
            self.statusBar().showMessage(
                "Timeline controls: Space plays/pauses; Play Review loops one selected range or chord; Prev/Next Chord or Alt+Left/Right steps through chords for review; Fit Song or Ctrl+Alt+0 shows the full song; Ctrl+Alt+F fits the selected review target; drag the chord lane or Shift+drag the timeline to select a chord-analysis range; Ctrl+drag adds another selected range; Esc clears selection; click/drag sets playhead; wheel scrolls vertically; Shift+wheel scrolls horizontally; Ctrl+wheel zooms time; Ctrl+Shift+wheel zooms pitch; middle/right drag pans.",
                12000,
            )

        def toggle_playback_from_shortcut(self) -> None:
            focused = QApplication.focusWidget()
            interactive_widgets = (
                QCheckBox,
                QComboBox,
                QDoubleSpinBox,
                QLineEdit,
                QListWidget,
                QPushButton,
                QSlider,
                QSpinBox,
                QTextEdit,
            )
            if isinstance(focused, interactive_widgets):
                return
            self.toggle_playback()

        def set_audio_path(self, path: Path) -> None:
            gui_project_flow.set_audio_path(self, path)

        def open_project_manifest(self, manifest_path: Path) -> None:
            gui_project_flow.open_project_manifest(self, manifest_path)

        def start_full_processing(self) -> None:
            gui_processing.start_full_processing(self)

        def start_midi_processing(self) -> None:
            gui_processing.start_midi_processing(self)

        def cancel_processing(self) -> bool:
            return gui_processing.cancel_processing(self)

        def start_worker_token(self) -> int:
            return gui_processing.start_worker_token(self)

        def invalidate_worker_token(self) -> None:
            gui_processing.invalidate_worker_token(self)

        def flush_messages(self) -> None:
            gui_processing.flush_messages(self)

        def is_active_worker_token(self, token: int) -> bool:
            return self.worker_jobs.is_active(token)

        def append_log(self, message: str) -> None:
            self.logger.info(message)
            self.log.append(message)

        def set_current_result(self, result: PipelineResult, open_output: bool = True) -> None:
            gui_editor_load.set_current_result(self, result, open_output)

        def start_editor_project_load(self, result: PipelineResult, token: int) -> None:
            gui_editor_load.start_editor_project_load(self, result, token)

        def finish_editor_project_load(self, token: int, loaded: EditorLoadResult) -> None:
            gui_editor_load.finish_editor_project_load(self, token, loaded)

        def finish_editor_project_load_failed(self, token: int, project_dir: Path, error: str) -> None:
            gui_editor_load.finish_editor_project_load_failed(self, token, project_dir, error)

        def finish_editor_load_activity(self, token: int, message: str) -> None:
            gui_editor_load.finish_editor_load_activity(self, token, message)

        def apply_manual_chords(self) -> None:
            gui_editor_state.apply_manual_chords(self)

        def refresh_editor_project_from_chord_edits(self, selected_chord: ChordRegion | None = None) -> None:
            gui_editor_state.refresh_editor_project_from_chord_edits(self, selected_chord)

        def refresh_editor_lists(self, track_visibility: dict[str, bool] | None = None) -> None:
            gui_editor_load.refresh_editor_lists(self, track_visibility)

        def refresh_detected_chord_list(self) -> None:
            gui_editor_load.refresh_detected_chord_list(self)

        def refresh_playback_controls(self, editor_state: dict) -> None:
            rebuild_track_controls(self, editor_state)

        def handle_midi_track_toggled(self, stem_name: str, checked: bool) -> None:
            if checked and self.current_result is not None and stem_name not in self.transport.midi_preview_paths:
                self.start_midi_preview_render(self.current_result, {stem_name})
            self.refresh_playback_mix()
            self.refresh_timeline_track_summaries()
            self.save_editor_state()

        def refresh_timeline_track_summaries(self) -> None:
            self.sync_track_control_panel()

        def sync_track_control_panel(self) -> None:
            sync_track_controls(self)

        def sync_track_control_scroll(self, value: int) -> None:
            scrollbar = self.playback_scroll.verticalScrollBar()
            if scrollbar.value() != value:
                scrollbar.setValue(value)

        def sync_timeline_scroll(self, value: int) -> None:
            scrollbar = self.timeline.verticalScrollBar()
            if scrollbar.value() != value:
                scrollbar.setValue(value)

        def prepare_transport_players(self, result: PipelineResult) -> None:
            gui_transport_flow.prepare_transport_players(self, result)

        def clear_transport_players(self) -> None:
            self.transport.clear_players()

        def find_existing_midi_previews(self, result: PipelineResult) -> dict[str, Path]:
            return find_existing_midi_previews(result)

        def start_midi_preview_render(
            self,
            result: PipelineResult,
            requested_stems: set[str] | None = None,
        ) -> None:
            gui_transport_flow.start_midi_preview_render(self, result, requested_stems)

        def _midi_preview_worker_running(self, project_dir: Path, stem_name: str) -> bool:
            return gui_transport_flow.midi_preview_worker_running(self, project_dir, stem_name)

        def clear_midi_preview_worker(self, project_dir: Path, stem_name: str, token: int) -> None:
            gui_transport_flow.clear_midi_preview_worker(self, project_dir, stem_name, token)

        def attach_midi_preview_players(self, previews: dict[str, Path], finish_activity: bool = True) -> None:
            gui_transport_flow.attach_midi_preview_players(self, previews, finish_activity)

        def refresh_playback_mix(self) -> None:
            self.transport.refresh_mix()
            self.apply_midi_transport_state()

        def midi_track_enabled(self, stem_name: str) -> bool:
            return self.transport.midi_track_enabled(stem_name)

        def apply_midi_transport_state(self) -> None:
            self.transport.apply_midi_transport_state(self.timeline.position)

        def toggle_playback(self) -> None:
            gui_transport_flow.toggle_playback(self)

        def play_transport(self) -> None:
            gui_transport_flow.play_transport(self)

        def pause_transport(self) -> None:
            gui_transport_flow.pause_transport(self)

        def stop_transport(self) -> None:
            gui_transport_flow.stop_transport(self)

        def seek_audio_players(self, seconds: float) -> None:
            self.transport.seek(seconds)

        def update_transport_position(self) -> None:
            gui_transport_flow.update_transport_position(self)

        def transport_master_player(self) -> QMediaPlayer | None:
            return self.transport.master_player()

        def resync_transport_players(self, master: QMediaPlayer | None = None) -> None:
            self.transport.resync(master)

        def loop_playback_start_seconds(self) -> float:
            return loop_playback_start(self.timeline.position, self.loop_playback_range())

        def loop_playback_range(self) -> tuple[float, float] | None:
            return review_playback_loop_range(self.timeline.selection_ranges(), self.timeline.selected_chord)

        def set_editor_position_seconds(
            self,
            seconds: float,
            save: bool = True,
            seek_players: bool = True,
            force_harmony_refresh: bool = False,
        ) -> None:
            if self.editor_project is not None:
                seconds = max(0.0, min(seconds, max(self.editor_project.duration, 0.0)))
            self.editor_position.setText(format_time(seconds))
            self.timeline.set_position(seconds)
            self.refresh_current_harmony(seconds, force=force_harmony_refresh)
            if seek_players:
                self.seek_audio_players(seconds)
            if save:
                self.request_editor_state_save()

        def set_editor_selection(self, selection: tuple[float, float] | None) -> None:
            gui_editor_actions.set_editor_selection(self, selection)

        def clear_editor_selection(self) -> None:
            self.timeline.clear_selection()
            self.refresh_current_harmony(self.timeline.position, force=True)

        def select_review_chord(self, direction: int) -> None:
            gui_editor_actions.select_review_chord(self, direction)

        def set_chord_context_text(self, text: str) -> None:
            self.chord_context.setText(text)
            self.chord_context.setToolTip(text)

        def refresh_current_theory(self, source_notes: list[NoteEvent], seconds: float) -> None:
            gui_harmony_flow.refresh_current_theory(self, source_notes, seconds)

        def set_theory_analysis(self, analysis: TheoryAnalysis | None) -> None:
            self.current_theory_analysis = analysis
            self.theory_list.clear()
            has_candidates = bool(analysis and analysis.candidates)
            self.inspect_theory_button.setEnabled(has_candidates)
            if not has_candidates or analysis is None:
                self.theory_context.setText("Theory: -")
                self.theory_context.setToolTip("No scale, key, or mode evidence yet.")
                return
            note_text = ", ".join(
                f"{self.display_weighted_note_name(name)} ({weight:.0%})"
                for name, weight in analysis.note_weights[:8]
            )
            self.theory_context.setText(
                f"Likely: {analysis.label} (score {analysis.confidence:.0%})\n"
                f"Weighted notes: {note_text or '-'}"
            )
            self.theory_context.setToolTip(self.theory_context.text())
            for candidate in analysis.candidates[:8]:
                notes = " - ".join(candidate.notes)
                item = QListWidgetItem(
                    f"{candidate.label}  {candidate.score:.0%}\n"
                    f"{notes}\n"
                    f"fit {candidate.pitch_fit:.0%}, centre {candidate.center_strength:.0%}, "
                    f"chords {candidate.chord_support:.0%}"
                )
                item.setToolTip("\n".join(candidate.explanation))
                self.theory_list.addItem(item)
            if analysis.progression is not None:
                self.theory_list.addItem(
                    "Progression\n"
                    f"{' - '.join(analysis.progression.chord_labels) or '-'}\n"
                    f"{' - '.join(analysis.progression.roman_numerals) or '-'}"
                )
            if analysis.core_notes or analysis.scale_notes:
                self.theory_list.addItem(
                    "Playable notes\n"
                    f"Core: {' - '.join(analysis.core_notes) or '-'}\n"
                    f"Scale: {' - '.join(analysis.scale_notes) or '-'}"
                )

        def refresh_current_gap_suggestions(self, source_notes: list[NoteEvent]) -> None:
            gui_harmony_flow.refresh_current_gap_suggestions(self, source_notes)

        def current_chord_gap_range(self) -> tuple[float, float] | None:
            return gui_harmony_flow.current_chord_gap_range(self)

        def set_gap_analysis(self, analysis: ChordGapAnalysis | None) -> None:
            harmony_panel.set_gap_analysis(self, analysis)

        def refresh_gap_suggestion_actions(self) -> None:
            harmony_panel.refresh_gap_suggestion_actions(self)

        def chord_min_note_floor(self) -> float:
            return self.min_note_evidence_slider.value() / 100

        def chord_scoring_options(self) -> ChordScoringOptions:
            return ChordScoringOptions(weak_note_floor=self.chord_min_note_floor())

        def selected_notation_preference(self) -> str:
            return self.notation_spelling.currentData() or "auto"

        def resolved_notation_preference(self, chord_label: str | None = None) -> str:
            return resolve_notation_preference(
                self.selected_notation_preference(),
                self.current_theory_analysis.label if self.current_theory_analysis else None,
                chord_label,
            )

        def display_chord(self, label: str | None) -> str:
            if not label:
                return "No clear chord"
            return display_chord_label(label, self.resolved_notation_preference(label))

        def display_chord_tones(self, label: str) -> list[str]:
            return chord_tones_for_label(label, self.resolved_notation_preference(label))

        def display_chord_bass(self, label: str) -> str | None:
            return chord_bass_name_for_label(label, self.resolved_notation_preference(label))

        def display_note_name(self, pitch: int) -> str:
            return midi_note_name(pitch, self.resolved_notation_preference())

        def display_pitch_class_name(self, pitch_class: int) -> str:
            return pitch_class_name(pitch_class, self.resolved_notation_preference())

        def display_weighted_note_name(self, note_name: str) -> str:
            pitch_class = pitch_class_for_name(note_name)
            if pitch_class is None:
                return note_name
            return self.display_pitch_class_name(pitch_class)

        def handle_min_note_evidence_changed(self, value: int) -> None:
            self.min_note_evidence_label.setText(f"Min note evidence: {value}%")
            self.refresh_current_harmony(self.timeline.position, force=True)

        def handle_notation_spelling_changed(self, *_args) -> None:
            self.timeline.set_note_name_formatter(self.display_note_name)
            self.refresh_current_harmony(self.timeline.position, force=True)

        def refresh_current_harmony(self, seconds: float, force: bool = False) -> None:
            if self.harmony_refresh_gate.should_refresh(time.monotonic(), force=force):
                gui_harmony_flow.refresh_current_harmony(self, seconds)

        def update_harmony_context(self, mode: str) -> None:
            self.current_harmony_context = HarmonyContext(
                mode=mode,
                sampled_tracks=tuple(self.chord_analysis_track_names()),
            )

        def chord_analysis_track_names(self) -> list[str]:
            return inspector_chord_analysis_track_names(
                self.editor_project,
                gui_harmony_flow.selected_chord_analysis_tracks(self),
            )

        def handle_chord_note_filter_changed(self, item) -> None:
            gui_harmony_flow.handle_chord_note_filter_changed(self, item)

        def reset_chord_note_filter(self) -> None:
            gui_harmony_flow.reset_chord_note_filter(self)

        def inspect_current_chord_analysis(self) -> None:
            gui_harmony_dialogs.inspect_current_chord_analysis(self)

        def inspect_current_theory_analysis(self) -> None:
            gui_harmony_dialogs.inspect_current_theory_analysis(self)

        def inspect_current_gap_suggestions(self) -> None:
            gui_harmony_dialogs.inspect_current_gap_suggestions(self)

        def use_selected_gap_suggestion(self) -> None:
            if self.current_chord_gap_analysis is None:
                return
            item = self.gap_suggestion_list.currentItem()
            if item is None or item.data(Qt.UserRole) is None:
                return
            suggestion = self.current_chord_gap_analysis.suggestions[int(item.data(Qt.UserRole))]
            chord = ChordRegion(
                start=suggestion.start,
                end=suggestion.end,
                label=suggestion.label,
                confidence=suggestion.score,
            )
            self.insert_manual_chord(chord)
            self.refresh_editor_project_from_chord_edits(chord)
            self.statusBar().showMessage(
                f"Filled gap with {self.display_chord(suggestion.label)}: "
                f"{format_time(suggestion.start)} - {format_time(suggestion.end)}.",
                5000,
            )

        def select_first_chord_candidate(self) -> None:
            harmony_panel.select_first_chord_candidate(self)

        def handle_chord_selection_changed(self, *_args) -> None:
            self.refresh_chord_actions()
            self.refresh_chord_keyboard()

        def refresh_chord_keyboard(self) -> None:
            harmony_panel.refresh_chord_keyboard(self)

        def active_chord_track_region(self) -> ChordRegion | None:
            return harmony_panel.active_chord_track_region(self)

        def refresh_chord_actions(self) -> None:
            harmony_panel.refresh_chord_actions(self)

        def preview_selected_chord(self) -> None:
            self.preview_chord_item(self.chord_list.currentItem())

        def preview_chord_item(self, item) -> None:
            if item is None or self.current_result is None:
                return
            label = item.data(Qt.UserRole)
            note_names = item.data(Qt.UserRole + 2) or []
            if not label or not note_names:
                return
            notes = self.preview_notes_for_chord(label, note_names)
            preview_dir = self.current_result.project_dir / "editor" / "chord-preview"
            if not safe_qt_multimedia_call(
                self.logger,
                "Chord preview reset failed",
                lambda: reset_player_source(self.chord_preview_player),
            ):
                return
            preview = render_note_preview("official-chord", notes, preview_dir)
            if not preview:
                return
            if safe_qt_multimedia_call(
                self.logger,
                "Chord preview playback failed",
                lambda: start_player_source(self.chord_preview_player, QUrl.fromLocalFile(str(preview))),
            ):
                self.statusBar().showMessage(f"Playing official {self.display_chord(label)} chord.", 3000)

        def preview_notes_for_chord(self, label: str, note_names: list[str]) -> list[NoteEvent]:
            pitches = chord_preview_pitches(label, note_names)
            return [
                NoteEvent(
                    stem="official-chord",
                    start=0.0,
                    end=1.45,
                    pitch=pitch,
                    velocity=92,
                )
                for pitch in pitches
            ]

        def assign_selected_chord_to_selection(self) -> None:
            gui_editor_state.assign_selected_chord_to_selection(self)

        def delete_selected_chord(self) -> None:
            gui_editor_state.delete_selected_chord(self)

        def insert_manual_chord(self, chord: ChordRegion) -> None:
            gui_editor_state.insert_manual_chord(self, chord)

        def edit_timeline_chord(self, original: ChordRegion, edited: ChordRegion) -> None:
            gui_editor_state.edit_timeline_chord(self, original, edited)

        def delete_timeline_chord(self, chord: ChordRegion) -> None:
            gui_editor_state.delete_timeline_chord(self, chord)

        def show_timeline_chord_status(self, chord: ChordRegion | None) -> None:
            gui_editor_state.show_timeline_chord_status(self, chord)

        def refresh_visible_tracks(self) -> None:
            gui_editor_state.refresh_visible_tracks(self)

        def show_all_timeline_tracks(self) -> None:
            gui_editor_state.show_all_timeline_tracks(self)

        def save_editor_state(self) -> bool:
            return gui_editor_state.save_editor_state(self)

        def request_editor_state_save(self, delay_ms: int = 750) -> None:
            gui_editor_state.request_editor_state_save(self, delay_ms)

        def reset_stage_state(self, _path: Path | None = None) -> None:
            gui_project_flow.reset_stage_state(self, _path)

        def update_import_clip_status(self, clip_range=None, duration_seconds: float | None = None) -> None:
            self.stop_import_clip_preview()
            duration = self.import_clip_picker.duration_seconds if duration_seconds is None else duration_seconds
            self.import_clip_status.setText(clip_status_text(clip_range, duration))
            self.import_clip_play.setEnabled(
                self.import_clip_picker.path is not None
                and import_preview_range(clip_range, duration) is not None
                and self.worker_jobs.active_token is None
            )
            self.import_clip_clear.setEnabled(
                clip_range is not None and self.worker_jobs.active_token is None
            )

        def play_import_clip_preview(self) -> None:
            path = self.import_clip_picker.path
            bounds = import_preview_range(
                self.import_clip_picker.selected_clip_range(),
                self.import_clip_picker.duration_seconds,
            )
            if path is None or bounds is None:
                self.append_log("Choose an audio file and range before preview playback.")
                return
            self.pause_transport()
            start_seconds, end_seconds = bounds
            self.import_clip_preview_end_seconds = end_seconds
            source = QUrl.fromLocalFile(str(path))
            safe_qt_multimedia_call(
                self.logger,
                "Import preview playback failed",
                lambda: self._start_import_clip_player(source, start_seconds),
            )
            self.import_clip_play.setEnabled(False)
            self.import_clip_stop.setEnabled(True)
            self.import_clip_timer.start()

        def _start_import_clip_player(self, source: QUrl, start_seconds: float) -> None:
            self.import_clip_player.setSource(source)
            self.import_clip_player.setPosition(int(start_seconds * 1000))
            self.import_clip_player.play()

        def stop_import_clip_preview(self) -> None:
            self.import_clip_timer.stop()
            safe_qt_multimedia_call(
                self.logger,
                "Import preview stop failed",
                lambda: self.import_clip_player.pause(),
            )
            self.import_clip_preview_end_seconds = None
            if hasattr(self, "import_clip_stop"):
                self.import_clip_stop.setEnabled(False)
            if hasattr(self, "import_clip_play"):
                self.import_clip_play.setEnabled(
                    self.import_clip_picker.path is not None
                    and import_preview_range(
                        self.import_clip_picker.selected_clip_range(),
                        self.import_clip_picker.duration_seconds,
                    )
                    is not None
                    and self.worker_jobs.active_token is None
                )

        def poll_import_clip_preview(self) -> None:
            end_seconds = self.import_clip_preview_end_seconds
            if end_seconds is None:
                self.stop_import_clip_preview()
                return
            if self.import_clip_player.position() >= int(end_seconds * 1000):
                self.stop_import_clip_preview()

        def set_processing_state(self, busy: bool) -> None:
            gui_pipeline_state.set_processing_state(self, busy)

        def selected_separation_options(self):
            return gui_pipeline_state.selected_separation_options(self)

        def selected_midi_options(self):
            return gui_pipeline_state.selected_midi_options(self)

        def selected_midi_stems(self) -> set[str]:
            return gui_pipeline_state.selected_midi_stems(self)

        def refresh_midi_stem_checks(self, *_args) -> None:
            gui_pipeline_state.refresh_midi_stem_checks(self, *_args)

        def refresh_model_details(self, *_args) -> None:
            gui_pipeline_state.refresh_model_details(self, *_args)

        def open_latest_output(self) -> None:
            gui_project_flow.open_latest_output(self)

        def open_logs_folder(self) -> None:
            gui_project_flow.open_logs_folder(self)

        def open_folder_path(self, target: Path, label: str) -> None:
            gui_project_flow.open_folder_path(self, target, label)

    def _double_spin(low: float, high: float, value: float, step: float, decimals: int) -> QDoubleSpinBox:
        spin = NoWheelDoubleSpinBox()
        spin.setRange(low, high)
        spin.setValue(value)
        spin.setSingleStep(step)
        spin.setDecimals(decimals)
        return spin

    def _frequency_spin(special: str) -> QDoubleSpinBox:
        spin = _double_spin(0.0, 20000.0, 0.0, 10.0, 1)
        spin.setSpecialValueText(special)
        return spin

    app = QApplication([])
    app.setStyleSheet(pitchstems_stylesheet())
    window = MainWindow()
    window.show()
    smoke_mode = os.environ.get("PITCHSTEMS_GUI_SMOKE")
    if smoke_mode in {"startup", "project", "real-audio"}:
        from pitchstems.gui_smoke import (
            capture_visual_audit,
            run_project_smoke,
            run_real_audio_project_smoke,
            run_startup_smoke,
        )

        def run_smoke_and_exit() -> None:
            try:
                run_startup_smoke(window)
                if smoke_mode == "project":
                    run_project_smoke(window)
                if smoke_mode == "real-audio":
                    manifest = os.environ.get("PITCHSTEMS_REAL_AUDIO_SMOKE_MANIFEST")
                    if not manifest:
                        raise RuntimeError("PITCHSTEMS_REAL_AUDIO_SMOKE_MANIFEST is required.")
                    run_real_audio_project_smoke(window, Path(manifest))
                visual_audit_dir = os.environ.get("PITCHSTEMS_VISUAL_AUDIT_DIR")
                if visual_audit_dir:
                    capture_visual_audit(window, Path(visual_audit_dir))
            except Exception:
                logger.exception("GUI startup smoke failed")
                app.exit(1)
                return
            app.exit(0)

        QTimer.singleShot(0, run_smoke_and_exit)
        QTimer.singleShot(10000, lambda: app.exit(2))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
