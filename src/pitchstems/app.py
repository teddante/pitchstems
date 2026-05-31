from __future__ import annotations

import os
import queue
import threading
from dataclasses import dataclass
from pathlib import Path

from pitchstems.acceleration import onnxruntime_status, torch_status
from pitchstems.app_logging import app_logger, logs_dir, setup_app_logging
from pitchstems.chord_preview import chord_preview_pitches
from pitchstems.chord_regions import merge_chord_ranges
from pitchstems.editor_project import (
    ChordAnalysis,
    ChordRegion,
    ChordScoringOptions,
    EditorProject,
    NoteEvent,
    active_notes_at,
    analyze_chord_at,
    analyze_chord_region,
    chord_bass_name_for_label,
    chord_tones_for_label,
    display_chord_label,
    midi_note_name,
)
from pitchstems.editor_loader import EditorLoadResult, apply_chord_edits, build_editor_load_result
from pitchstems.editor_state import (
    build_editor_state_snapshot,
    editor_float,
    save_editor_state_snapshot,
)
from pitchstems.file_opening import open_folder
from pitchstems.midi_preview import render_midi_preview, render_note_preview
from pitchstems.model_catalog import model_choice
from pitchstems.notation import pitch_class_for_name, pitch_class_name
from pitchstems.pipeline import PipelineResult
from pitchstems.project_store import (
    PROJECT_FILENAME,
    load_pipeline_result,
)
from pitchstems.harmony_inspector import (
    chord_analysis_track_names as inspector_chord_analysis_track_names,
    chord_base_pitch_weights as inspector_chord_base_pitch_weights,
    chord_note_constraints as inspector_chord_note_constraints,
    chord_sample_text as inspector_chord_sample_text,
    filtered_chord_analysis_notes as inspector_filtered_chord_analysis_notes,
    harmony_context_key as inspector_harmony_context_key,
    resolve_notation_preference,
    selected_chord_analysis_notes,
)
from pitchstems import harmony_panel
from pitchstems import gui_processing
from pitchstems.harmony_report import current_chord_analysis_report as build_chord_analysis_report
from pitchstems.gui_options import default_midi_checked, device_label, optional_frequency
from pitchstems.gui_track_controls import rebuild_track_controls, sync_track_control_panel as sync_track_controls
from pitchstems.recent_projects import (
    normalize_recent_project_paths,
    recent_project_label,
    remember_recent_project,
    remove_recent_project,
)
from pitchstems.separation import SeparationOptions, StemResult
from pitchstems.theory import (
    ChordGapAnalysis,
    TheoryAnalysis,
    analyze_chord_gap,
    analyze_theory_at,
    analyze_theory_region,
    chord_gap_report,
    theory_analysis_report,
)
from pitchstems.time_format import format_time
from pitchstems.transcription import MidiOptions

@dataclass(frozen=True)
class HarmonyContext:
    mode: str
    sampled_tracks: tuple[str, ...]
    source_note_count: int
    analyzed_note_count: int
    chord_analysis: ChordAnalysis | None
    theory_analysis: TheoryAnalysis | None
    gap_analysis: ChordGapAnalysis | None


def main() -> int:
    log_path = setup_app_logging()
    logger = app_logger()
    try:
        from PySide6.QtCore import QSettings, QTimer, Qt, QUrl
        from PySide6.QtGui import QAction, QKeySequence, QShortcut
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        from PySide6.QtWidgets import (
            QApplication,
            QCheckBox,
            QComboBox,
            QDialog,
            QDoubleSpinBox,
            QFileDialog,
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
            self.choice = model_choice("bs_roformer_sw")
            self.log_path = log_path
            self.logger = logger
            self.messages: queue.Queue[object] = queue.Queue()
            self.worker: threading.Thread | None = None
            self.worker_token = 0
            self.active_worker_token: int | None = None
            self.editor_load_worker: threading.Thread | None = None
            self.editor_load_token = 0
            self.editor_load_activity_tokens: set[int] = set()
            self.midi_preview_token = 0
            self.midi_preview_workers: dict[tuple[Path, str], tuple[int, threading.Thread]] = {}
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
            self.current_theory_analysis: TheoryAnalysis | None = None
            self.current_chord_gap_analysis: ChordGapAnalysis | None = None
            self.updating_chord_note_filter = False

            self.drop_zone = DropZone()
            self.drop_zone.on_path_changed = self.reset_stage_state
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

            self.model_title = QLabel()
            self.model_title.setStyleSheet("font-size: 18px; font-weight: 700;")
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
            self.onset_threshold = _double_spin(0.0, 1.0, 0.5, 0.05, 2)
            self.onset_threshold.setToolTip("Basic Pitch default: 0.50. Higher means fewer detected note attacks; lower means more sensitive note starts.")
            self.frame_threshold = _double_spin(0.0, 1.0, 0.3, 0.05, 2)
            self.frame_threshold.setToolTip("Basic Pitch default: 0.30. Higher means stricter sustained-note detection; lower keeps more quiet/ambiguous frames.")
            self.minimum_note_length = _double_spin(0.0, 1000.0, 127.7, 10.0, 1)
            self.minimum_note_length.setToolTip("Basic Pitch default: 127.7 ms. Notes shorter than this are filtered out.")
            self.minimum_frequency = _frequency_spin("No lower limit")
            self.minimum_frequency.setToolTip("Basic Pitch default: no lower frequency limit.")
            self.maximum_frequency = _frequency_spin("No upper limit")
            self.maximum_frequency.setToolTip("Basic Pitch default: no upper frequency limit.")
            self.midi_tempo = _double_spin(20.0, 300.0, 120.0, 1.0, 1)
            self.midi_tempo.setToolTip("Basic Pitch default: 120 BPM. This is MIDI metadata, not audio time-stretching.")
            self.melodia_trick = QCheckBox("Melodia post-processing (default on)")
            self.melodia_trick.setChecked(True)
            self.melodia_trick.setToolTip("Basic Pitch default. Helps turn frame/onset predictions into cleaner note events.")
            self.multiple_pitch_bends = QCheckBox("Separate pitch bends for overlapping notes (default off)")
            self.multiple_pitch_bends.setToolTip("Basic Pitch default: off. Useful for expressive material, but can make MIDI more complex.")
            self.save_notes = QCheckBox("Save note-event CSV (default on)")
            self.save_notes.setChecked(True)
            self.save_model_outputs = QCheckBox("Save raw model output NPZ (default off)")
            self.save_model_outputs.setToolTip("Basic Pitch default: off. Technical/debug output: contours, onsets, and note activations.")
            self.sonify_midi = QCheckBox("Render MIDI check audio (default off)")
            self.sonification_samplerate = NoWheelSpinBox()
            self.sonification_samplerate.setRange(8000, 192000)
            self.sonification_samplerate.setSingleStep(1000)
            self.sonification_samplerate.setValue(44100)
            self.sonification_samplerate.setEnabled(False)

            self.create_zip = QCheckBox("Create ZIP export package")
            self.create_zip.setChecked(False)
            self.create_zip.setToolTip("Optional. Creates a shareable ZIP without duplicating stem WAVs inside the project folder.")
            self.open_when_done = QCheckBox("Open output folder when finished")
            self.open_when_done.setChecked(False)

            self.run_full = QPushButton("Run separation + MIDI")
            self.run_midi = QPushButton("Rerun MIDI only")
            self.run_midi.setEnabled(False)
            self.log = QTextEdit()
            self.log.setReadOnly(True)
            self.editor_summary = QLabel("Run separation + MIDI to build an editor timeline.")
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
            self.chord_context.setMinimumHeight(74)
            self.chord_context.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            self.chord_context.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.chord_context.setStyleSheet("color: #475569;")
            self.note_filter_list = QListWidget()
            self.note_filter_list.setMinimumHeight(120)
            self.note_filter_list.setMaximumHeight(180)
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
            self.timeline_slider = QSlider(Qt.Horizontal)
            self.timeline_slider.setRange(0, 0)
            self.timeline_slider.setEnabled(False)
            self.timeline_slider.setVisible(False)
            self.track_list = QListWidget()
            self.track_list.setMaximumWidth(240)
            self.track_list.setAlternatingRowColors(True)
            self.playback_controls = QVBoxLayout()
            self.playback_controls.setSpacing(0)
            self.playback_controls.setContentsMargins(0, 0, 0, 0)
            self.playback_controls_widget = QWidget()
            self.playback_controls_widget.setLayout(self.playback_controls)
            self.playback_scroll = QScrollArea()
            self.playback_scroll.setWidgetResizable(True)
            self.playback_scroll.setWidget(self.playback_controls_widget)
            self.playback_scroll.setMinimumWidth(286)
            self.playback_scroll.setMaximumWidth(360)
            self.playback_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
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
            self.inspect_chord_button = QPushButton("Inspect")
            self.preview_chord_button.setEnabled(False)
            self.use_chord_button.setEnabled(False)
            self.inspect_chord_button.setEnabled(False)
            self.inspect_chord_button.setToolTip("Open a detailed report of the current harmony inputs, note weights, constraints, and chord candidate scoring.")
            self.chord_preview_player = QMediaPlayer(self)
            self.chord_preview_output = QAudioOutput(self)
            self.chord_preview_output.setVolume(0.85)
            self.chord_preview_player.setAudioOutput(self.chord_preview_output)
            self.play_button = QPushButton("Play")
            self.stop_button = QPushButton("Stop")
            self.stop_button.setEnabled(False)
            self.fit_song_button = QPushButton("Fit Song")
            self.fit_song_button.setEnabled(False)

            pipeline_page = build_pipeline_page(self)
            editor_page = build_editor_page(self)

            self.main_tabs = QTabWidget()
            self.main_tabs.addTab(pipeline_page, "Pipeline")
            self.main_tabs.addTab(editor_page, "Editor")

            root = QWidget()
            root_layout = QVBoxLayout()
            root_layout.setContentsMargins(0, 0, 0, 0)
            root_layout.addWidget(self.main_tabs)
            root.setLayout(root_layout)
            self.setCentralWidget(root)
            self.create_menus()
            self.activity_label = QLabel("Ready")
            self.activity_label.setMinimumWidth(180)
            self.activity_bar = QProgressBar()
            self.activity_bar.setRange(0, 1)
            self.activity_bar.setValue(1)
            self.activity_bar.setMaximumWidth(150)
            self.activity_bar.setTextVisible(False)
            self.statusBar().addPermanentWidget(self.activity_label)
            self.statusBar().addPermanentWidget(self.activity_bar)
            self.statusBar().showMessage(
                "Timeline: Space plays/pauses; drag chord lane or Shift+drag to select chord-analysis range; Esc clears selection; wheel scrolls, Ctrl+wheel zooms."
            )
            self.space_playback_shortcut = QShortcut(QKeySequence("Space"), self)
            self.space_playback_shortcut.setContext(Qt.ApplicationShortcut)
            self.space_playback_shortcut.activated.connect(self.toggle_playback_from_shortcut)
            self.clear_selection_shortcut = QShortcut(QKeySequence("Esc"), self)
            self.clear_selection_shortcut.setContext(Qt.ApplicationShortcut)
            self.clear_selection_shortcut.activated.connect(self.clear_editor_selection)

            self.run_full.clicked.connect(self.start_full_processing)
            self.run_midi.clicked.connect(self.start_midi_processing)
            self.play_button.clicked.connect(self.toggle_playback)
            self.stop_button.clicked.connect(self.stop_transport)
            self.fit_song_button.clicked.connect(self.fit_editor_song_to_view)
            self.preview_chord_button.clicked.connect(self.preview_selected_chord)
            self.use_chord_button.clicked.connect(self.assign_selected_chord_to_selection)
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
            self.timeline_slider.valueChanged.connect(self.set_editor_position)
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

        def create_menus(self) -> None:
            file_menu = self.menuBar().addMenu("&File")
            self._add_action(file_menu, "&Open Audio...", "Ctrl+O", self.pick_audio)
            self._add_action(file_menu, "Open &Project...", "Ctrl+Shift+O", self.pick_project)
            self.recent_projects_menu = file_menu.addMenu("Open &Recent")
            self.refresh_recent_projects_menu()
            file_menu.addSeparator()
            self._add_action(file_menu, "&Save Project", "Ctrl+S", self.save_project_now)
            self._add_action(file_menu, "Choose Output &Folder...", None, self.pick_output_dir)
            self._add_action(file_menu, "Open Output Folder", "Ctrl+E", self.open_latest_output)
            self._add_action(file_menu, "Open Logs Folder", None, self.open_logs_folder)
            file_menu.addSeparator()
            self._add_action(file_menu, "E&xit", "Alt+F4", self.close)

            run_menu = self.menuBar().addMenu("&Run")
            self._add_action(run_menu, "Run Separation + MIDI", "F5", self.start_full_processing)
            self._add_action(run_menu, "Rerun MIDI Only", "Shift+F5", self.start_midi_processing)

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
            self._add_action(view_menu, "Fit Whole Song", "Ctrl+Alt+0", self.fit_editor_song_to_view)

            help_menu = self.menuBar().addMenu("&Help")
            self._add_action(help_menu, "Show Timeline Controls", None, self.show_timeline_controls)

        def _add_action(self, menu, text: str, shortcut: str | None, callback) -> QAction:
            action = QAction(text, self)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(callback)
            menu.addAction(action)
            return action

        def refresh_recent_projects_menu(self) -> None:
            if self.recent_projects_menu is None:
                return
            self.recent_projects_menu.clear()
            recent = self.recent_project_paths()
            if not recent:
                action = QAction("No recent projects", self)
                action.setEnabled(False)
                self.recent_projects_menu.addAction(action)
                return
            for index, path in enumerate(recent[:10], 1):
                action = QAction(f"&{index} {self.recent_project_label(path)}", self)
                action.setToolTip(str(path))
                action.triggered.connect(lambda _checked=False, project_path=path: self.open_recent_project(project_path))
                self.recent_projects_menu.addAction(action)
            self.recent_projects_menu.addSeparator()
            self._add_action(self.recent_projects_menu, "Clear Recent Projects", None, self.clear_recent_projects)

        def recent_project_paths(self) -> list[Path]:
            return normalize_recent_project_paths(self.settings.value("recent_projects", []))

        def recent_project_label(self, manifest_path: Path) -> str:
            return recent_project_label(manifest_path)

        def remember_recent_project(self, project_dir: Path) -> None:
            recent = remember_recent_project(self.recent_project_paths(), project_dir)
            self.settings.setValue("recent_projects", [str(path) for path in recent])
            self.refresh_recent_projects_menu()

        def remove_recent_project(self, manifest_path: Path) -> None:
            recent = remove_recent_project(self.recent_project_paths(), manifest_path)
            self.settings.setValue("recent_projects", [str(path) for path in recent])
            self.refresh_recent_projects_menu()

        def clear_recent_projects(self) -> None:
            self.settings.setValue("recent_projects", [])
            self.refresh_recent_projects_menu()
            self.statusBar().showMessage("Recent projects cleared.", 3000)

        def open_recent_project(self, manifest_path: Path) -> None:
            if not manifest_path.exists():
                self.remove_recent_project(manifest_path)
                self.append_log(f"Recent project no longer exists: {manifest_path}")
                self.statusBar().showMessage("Recent project was removed because it no longer exists.", 5000)
                return
            self.open_project_manifest(manifest_path)

        def show_timeline_controls(self) -> None:
            self.statusBar().showMessage(
                "Timeline controls: Space plays/pauses; Fit Song or Ctrl+Alt+0 shows the full song; drag the chord lane or Shift+drag the timeline to select a chord-analysis range; Esc clears selection; click/drag sets playhead; wheel scrolls vertically; Shift+wheel scrolls horizontally; Ctrl+wheel zooms time; Ctrl+Shift+wheel zooms pitch; middle/right drag pans.",
                12000,
            )

        def fit_editor_song_to_view(self) -> None:
            if self.editor_project is None:
                self.statusBar().showMessage("Open or run a project before fitting the song view.", 4000)
                return
            self.timeline.fit_song_to_view()
            self.statusBar().showMessage("Showing the whole song horizontally and vertically.", 4000)

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

        def pick_audio(self) -> None:
            filename, _selected_filter = QFileDialog.getOpenFileName(
                self,
                "Open audio",
                str(Path.home()),
                "Audio files (*.wav *.mp3 *.flac *.m4a *.aac *.ogg);;All files (*.*)",
            )
            if filename:
                self.set_audio_path(Path(filename))

        def set_audio_path(self, path: Path) -> None:
            self.drop_zone.set_audio_file(path)
            self.reset_stage_state(path)

        def save_project_now(self) -> None:
            if self.current_result is None:
                self.append_log("No project is open yet.")
                return
            if self.save_editor_state():
                self.append_log(f"Saved project: {self.current_result.project_dir / PROJECT_FILENAME}")

        def pick_output_dir(self) -> None:
            directory = QFileDialog.getExistingDirectory(self, "Choose output directory")
            if directory:
                self.output_dir.setText(directory)

        def pick_project(self) -> None:
            filename, _selected_filter = QFileDialog.getOpenFileName(
                self,
                "Open PitchStems project",
                str(Path(self.output_dir.text())),
                f"PitchStems Project ({PROJECT_FILENAME});;JSON files (*.json)",
            )
            if not filename:
                return
            self.open_project_manifest(Path(filename))

        def open_project_manifest(self, manifest_path: Path) -> None:
            self.invalidate_worker_token()
            self.begin_activity("Opening project...")
            try:
                self.logger.info("Opening project manifest: %s", manifest_path)
                result = load_pipeline_result(manifest_path)
            except Exception as exc:
                self.logger.exception("Could not open project manifest")
                self.append_log(f"Could not open project: {exc}")
                self.end_activity("Could not open project")
                self.remove_recent_project(manifest_path)
                return
            self.output_dir.setText(str(result.project_dir.parent))
            self.drop_zone.set_project_file(result.project_dir, result.source_audio)
            try:
                self.logger.info("Building editor for project: %s", result.project_dir)
                self.set_current_result(result, open_output=False)
            except Exception as exc:
                self.logger.exception("Could not open project editor")
                self.append_log(f"Could not open project editor: {exc}")
                self.append_log(f"Log file: {self.log_path}")
                self.reset_stage_state()
                self.end_activity("Could not open project editor")
                return
            self.append_log(f"Opened project: {result.project_dir}")
            self.end_activity("Project loaded")

        def start_full_processing(self) -> None:
            gui_processing.start_full_processing(self)

        def start_midi_processing(self) -> None:
            gui_processing.start_midi_processing(self)

        def start_worker_token(self) -> int:
            return gui_processing.start_worker_token(self)

        def invalidate_worker_token(self) -> None:
            gui_processing.invalidate_worker_token(self)

        def flush_messages(self) -> None:
            gui_processing.flush_messages(self)

        def is_active_worker_token(self, token: int) -> bool:
            return self.active_worker_token == token

        def append_log(self, message: str) -> None:
            self.logger.info(message)
            self.log.append(message)

        def set_current_result(self, result: PipelineResult, open_output: bool = True) -> None:
            self.logger.info("Setting current result: %s", result.project_dir)
            self.stop_transport()
            self.set_activity_message("Loading result...")
            self.editor_load_token += 1
            self.current_result = result
            self.midi_preview_token += 1
            self.midi_preview_workers.clear()
            self.current_stems = result.stems
            self.current_input_stem = (result.source_audio or result.normalized_audio).stem
            self.latest_output_dir = result.project_dir
            self.base_editor_project = None
            self.editor_project = None
            self.manual_chords = []
            self.removed_chord_ranges = []
            self.rendering_midi_previews.clear()
            self.run_midi.setEnabled(True)
            self.separation_status.setText(f"Ready: {len(result.stems)} stems saved in {result.project_dir / 'stems'}")
            self.midi_status.setText(
                f"Ready: {len(result.midi_files)} MIDI files. Change Basic Pitch settings or MIDI stem ticks, then use Rerun MIDI only."
            )
            self.editor_summary.setText("Building editor timeline...")
            self.timeline_slider.setEnabled(False)
            self.fit_song_button.setEnabled(False)
            self.clear_transport_players()
            self.remember_recent_project(result.project_dir)
            if open_output and self.open_when_done.isChecked():
                self.open_latest_output()
            self.start_editor_project_load(result, self.editor_load_token)

        def start_editor_project_load(self, result: PipelineResult, token: int) -> None:
            self.logger.info("Starting editor project load: %s", result.project_dir)
            self.editor_load_activity_tokens.add(token)
            self.begin_activity("Building editor project...")

            def worker() -> None:
                try:
                    loaded = build_editor_load_result(result)
                    self.messages.put(("EDITOR_LOADED", token, loaded))
                except Exception as exc:
                    self.logger.exception("Editor project load failed")
                    self.messages.put(("EDITOR_LOAD_FAILED", token, result.project_dir, f"{exc}"))

            self.editor_load_worker = threading.Thread(
                target=worker,
                name="PitchStemsEditorLoad",
                daemon=True,
            )
            self.editor_load_worker.start()

        def finish_editor_project_load(self, token: int, loaded: EditorLoadResult) -> None:
            if token != self.editor_load_token or self.current_result is None:
                self.logger.info("Ignored stale editor load for %s", loaded.pipeline_result.project_dir)
                self.finish_editor_load_activity(token, "Ready")
                return
            if self.current_result.project_dir != loaded.pipeline_result.project_dir:
                self.logger.info("Ignored editor load for inactive project: %s", loaded.pipeline_result.project_dir)
                self.finish_editor_load_activity(token, "Ready")
                return

            self.base_editor_project = loaded.base_project
            self.editor_project = loaded.editor_project
            editor_state = loaded.editor_state
            self.manual_chords = loaded.manual_chords
            self.removed_chord_ranges = loaded.removed_chord_ranges
            self.logger.info(
                "Editor model built: tracks=%d notes=%d chords=%d",
                len(self.editor_project.tracks),
                len(self.editor_project.notes),
                len(self.editor_project.chords),
            )
            project = self.editor_project
            track_visibility = editor_state.get("track_visibility", {})
            notation_spelling = editor_state.get("notation_spelling", "auto")
            notation_index = self.notation_spelling.findData(notation_spelling)
            if notation_index >= 0:
                self.notation_spelling.blockSignals(True)
                self.notation_spelling.setCurrentIndex(notation_index)
                self.notation_spelling.blockSignals(False)
            playhead_seconds = editor_float(editor_state.get("playhead_seconds"), 0.0, low=0.0)
            self.editor_summary.setText(
                f"Editor project: {len(project.tracks)} tracks, {len(project.notes)} notes, "
                f"{len(project.chords)} chord regions."
            )
            maximum = max(0, int(project.duration * 1000))
            self.timeline_slider.blockSignals(True)
            self.timeline_slider.setRange(0, maximum)
            self.timeline_slider.setValue(0)
            self.timeline_slider.setEnabled(maximum > 0)
            self.timeline_slider.blockSignals(False)
            self.fit_song_button.setEnabled(maximum > 0)
            self.editor_position.setText(format_time(playhead_seconds))
            self.refresh_editor_lists(track_visibility)
            self.refresh_playback_controls(editor_state)
            self.clear_transport_players()
            self.logger.info("Drawing editor timeline")
            self.set_activity_message("Drawing editor timeline...")
            self.timeline.set_project(project)
            self.timeline.set_visible_tracks(
                {track.name for track in project.tracks if track_visibility.get(track.name, True)}
            )
            self.set_editor_position_seconds(playhead_seconds)
            self.main_tabs.setCurrentIndex(1)
            self.logger.info("Editor project loaded")
            self.finish_editor_load_activity(token, "Editor project loaded")

        def finish_editor_project_load_failed(self, token: int, project_dir: Path, error: str) -> None:
            if token != self.editor_load_token:
                self.logger.info("Ignored stale editor load failure for %s: %s", project_dir, error)
                self.finish_editor_load_activity(token, "Ready")
                return
            self.logger.error("Could not open project editor for %s: %s", project_dir, error)
            self.append_log(f"Could not open project editor: {error}")
            self.append_log(f"Log file: {self.log_path}")
            self.editor_summary.setText("Could not build editor timeline.")
            self.timeline.set_project(None)
            self.finish_editor_load_activity(token, "Could not open project editor")

        def finish_editor_load_activity(self, token: int, message: str) -> None:
            if token not in self.editor_load_activity_tokens:
                return
            self.editor_load_activity_tokens.discard(token)
            self.end_activity(message)

        def apply_manual_chords(self) -> None:
            if self.editor_project is None or (not self.manual_chords and not self.removed_chord_ranges):
                return
            self.editor_project = apply_chord_edits(
                self.editor_project,
                self.manual_chords,
                self.removed_chord_ranges,
            )

        def refresh_editor_project_from_chord_edits(self, selected_chord: ChordRegion | None = None) -> None:
            if self.current_result is None or self.base_editor_project is None:
                return
            position = self.timeline.position
            selection_start = self.timeline.selection_start
            selection_end = self.timeline.selection_end
            self.editor_project = self.base_editor_project
            self.apply_manual_chords()
            self.timeline.project = self.editor_project
            self.timeline._index_project()
            self.timeline.visible_tracks = {
                stem_name.lower()
                for stem_name, checkbox in self.track_visibility_checks.items()
                if checkbox.isChecked()
            }
            self.timeline.position = position
            self.timeline.selection_start = selection_start
            self.timeline.selection_end = selection_end
            self.timeline.selected_chord = selected_chord
            self.timeline.redraw()
            self.refresh_detected_chord_list()
            self.save_editor_state()

        def refresh_editor_lists(self, track_visibility: dict[str, bool] | None = None) -> None:
            track_visibility = track_visibility or {}
            self.editor_track_visibility = track_visibility
            self.track_note_counts = {}
            self.chord_list.clear()
            self.refresh_chord_keyboard()
            if self.editor_project is None:
                return
            for note in self.editor_project.notes:
                self.track_note_counts[note.stem] = self.track_note_counts.get(note.stem, 0) + 1
            self.refresh_detected_chord_list()

        def refresh_detected_chord_list(self) -> None:
            self.chord_list.clear()
            if self.editor_project is None:
                return
            for chord in self.editor_project.chords[:200]:
                self.chord_list.addItem(
                    f"{format_time(chord.start)}  {self.display_chord(chord.label)}  ({chord.confidence:.0%})"
                )
            if len(self.editor_project.chords) > 200:
                self.chord_list.addItem(f"... {len(self.editor_project.chords) - 200} more")
            self.refresh_chord_actions()
            self.refresh_chord_keyboard()

        def set_editor_position(self, value: int) -> None:
            self.set_editor_position_seconds(value / 1000)

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
            self.set_activity_message("Preparing audio players...")
            self.pause_transport()
            self.transport.prepare_players(result)
            self.attach_midi_preview_players(dict(self.transport.midi_preview_paths), finish_activity=False)
            requested_midi = {
                stem_name
                for stem_name, checkbox in self.track_midi_checks.items()
                if checkbox.isChecked() and stem_name not in self.transport.midi_preview_paths
            }
            if requested_midi:
                self.start_midi_preview_render(result, requested_midi)
            self.refresh_playback_mix()

        def clear_transport_players(self) -> None:
            self.transport.clear_players()

        def transport_players(self) -> list[QMediaPlayer]:
            return self.transport.players()

        def find_existing_midi_previews(self, result: PipelineResult) -> dict[str, Path]:
            return find_existing_midi_previews(result)

        def start_midi_preview_render(
            self,
            result: PipelineResult,
            requested_stems: set[str] | None = None,
        ) -> None:
            if self.editor_project is None or not self.editor_project.notes:
                return
            requested_keys = {stem.lower() for stem in (requested_stems or set())}
            missing = [
                track.name
                for track in self.editor_project.tracks
                if (not requested_keys or track.name.lower() in requested_keys)
                if track.name not in self.transport.midi_preview_paths
                and any(note.stem.lower() == track.name.lower() for note in self.editor_project.notes)
                and not self._midi_preview_worker_running(result.project_dir, track.name)
            ]
            if not missing:
                return
            project = self.editor_project
            preview_dir = result.project_dir / "editor" / "midi-preview"
            token = self.midi_preview_token
            self.rendering_midi_previews.update(missing)
            self.refresh_timeline_track_summaries()
            self.append_log(f"Rendering MIDI preview audio for {', '.join(missing)} in the background...")
            self.begin_activity("Rendering MIDI preview audio...")

            def worker() -> None:
                previews: dict[str, Path] = {}
                try:
                    for stem_name in missing:
                        preview = render_midi_preview(
                            stem_name,
                            project.notes,
                            preview_dir,
                            project.duration,
                        )
                        if preview:
                            previews[stem_name] = preview
                    self.messages.put(("MIDI_PREVIEWS", token, result.project_dir, set(missing), previews))
                except Exception as exc:
                    self.logger.exception("MIDI preview render failed")
                    self.messages.put(
                        (
                            "MIDI_PREVIEW_FAILED",
                            token,
                            result.project_dir,
                            set(missing),
                            f"Could not render MIDI previews: {exc}",
                        )
                    )

            worker_thread = threading.Thread(target=worker, daemon=True)
            for stem_name in missing:
                self.midi_preview_workers[(result.project_dir, stem_name.lower())] = (token, worker_thread)
            worker_thread.start()

        def _midi_preview_worker_running(self, project_dir: Path, stem_name: str) -> bool:
            key = (project_dir, stem_name.lower())
            entry = self.midi_preview_workers.get(key)
            if entry is None:
                return False
            token, worker = entry
            if token != self.midi_preview_token or not worker.is_alive():
                self.midi_preview_workers.pop(key, None)
                return False
            return True

        def clear_midi_preview_worker(self, project_dir: Path, stem_name: str, token: int) -> None:
            key = (project_dir, stem_name.lower())
            entry = self.midi_preview_workers.get(key)
            if entry is not None and entry[0] == token:
                self.midi_preview_workers.pop(key, None)

        def attach_midi_preview_players(self, previews: dict[str, Path], finish_activity: bool = True) -> None:
            if not previews:
                self.refresh_timeline_track_summaries()
                if finish_activity:
                    self.end_activity("No MIDI preview audio rendered")
                return
            for stem_name in previews:
                self.rendering_midi_previews.discard(stem_name)
            self.transport.attach_midi_preview_players(previews, self.timeline.position)
            self.refresh_playback_mix()
            self.refresh_timeline_track_summaries()
            if finish_activity:
                self.append_log(f"MIDI preview audio ready: {len(previews)} tracks.")
                self.end_activity("MIDI preview audio ready")

        def refresh_playback_mix(self) -> None:
            self.transport.refresh_mix()
            self.apply_midi_transport_state()

        def midi_track_enabled(self, stem_name: str) -> bool:
            return self.transport.midi_track_enabled(stem_name)

        def apply_midi_transport_state(self) -> None:
            self.transport.apply_midi_transport_state(self.timeline.position)

        def toggle_playback(self) -> None:
            if self.transport.is_playing:
                self.pause_transport()
            else:
                self.play_transport()

        def play_transport(self) -> None:
            if self.editor_project is None or self.current_result is None:
                self.append_log("Open or run a project before playback.")
                return
            if not self.transport.track_players:
                self.append_log("Preparing playback...")
                self.begin_activity("Preparing playback...")
                self.prepare_transport_players(self.current_result)
                self.end_activity("Playback ready")
            self.refresh_playback_mix()
            start_position = self.loop_playback_start_seconds()
            if start_position != self.timeline.position:
                self.set_editor_position_seconds(start_position, save=False, seek_players=False)
            self.transport.play(start_position)
            self.play_button.setText("Pause")
            self.stop_button.setEnabled(True)
            self.transport_timer.start(80)
            QTimer.singleShot(250, self.resync_transport_players)

        def pause_transport(self) -> None:
            if not self.transport.pause():
                return
            self.play_button.setText("Play")
            self.transport_timer.stop()
            self.save_editor_state()

        def stop_transport(self) -> None:
            self.transport.stop()
            self.play_button.setText("Play")
            self.stop_button.setEnabled(False)
            self.transport_timer.stop()
            if self.editor_project is not None:
                self.set_editor_position_seconds(0.0, seek_players=False)

        def seek_audio_players(self, seconds: float) -> None:
            self.transport.seek(seconds)

        def update_transport_position(self) -> None:
            master = self.transport_master_player()
            if master is None:
                return
            seconds = master.position() / 1000
            self.resync_transport_players(master)
            selection = self.timeline.selection_range()
            if selection is not None:
                start, end = selection
                if seconds >= end:
                    self.seek_audio_players(start)
                    self.set_editor_position_seconds(start, save=False, seek_players=False)
                    return
            self.set_editor_position_seconds(seconds, save=False, seek_players=False)

        def transport_master_player(self) -> QMediaPlayer | None:
            return self.transport.master_player()

        def resync_transport_players(self, master: QMediaPlayer | None = None) -> None:
            self.transport.resync(master)

        def loop_playback_start_seconds(self) -> float:
            return loop_playback_start(self.timeline.position, self.timeline.selection_range())

        def set_editor_position_seconds(
            self,
            seconds: float,
            save: bool = True,
            seek_players: bool = True,
        ) -> None:
            if self.editor_project is not None:
                seconds = max(0.0, min(seconds, max(self.editor_project.duration, 0.0)))
            value = int(seconds * 1000)
            self.timeline_slider.blockSignals(True)
            self.timeline_slider.setValue(value)
            self.timeline_slider.blockSignals(False)
            self.editor_position.setText(format_time(seconds))
            self.timeline.set_position(seconds)
            self.refresh_current_harmony(seconds)
            if seek_players:
                self.seek_audio_players(seconds)
            if save:
                self.request_editor_state_save()

        def set_editor_selection(self, selection: tuple[float, float] | None) -> None:
            self.refresh_current_harmony(self.timeline.position)
            self.refresh_chord_actions()
            if selection is None:
                self.statusBar().showMessage("Timeline selection cleared.", 3000)
                return
            start, end = selection
            self.statusBar().showMessage(
                f"Loop selection active: {format_time(start)} - {format_time(end)}. Press Play to loop this range.",
                5000,
            )

        def clear_editor_selection(self) -> None:
            self.timeline.clear_selection()
            self.refresh_current_harmony(self.timeline.position)

        def set_chord_context_text(self, text: str) -> None:
            self.chord_context.setText(text)
            self.chord_context.setToolTip(text)

        def refresh_current_theory(self, source_notes: list[NoteEvent], seconds: float) -> None:
            if self.editor_project is None:
                self.set_theory_analysis(None)
                return
            selection = self.timeline.selection_range()
            if selection is not None:
                start, end = selection
                analysis = analyze_theory_region(source_notes, self.editor_project.chords, start, end)
            else:
                analysis = analyze_theory_at(source_notes, self.editor_project.chords, seconds)
            self.set_theory_analysis(analysis)

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
            if self.editor_project is None:
                self.set_gap_analysis(None)
                return
            gap = self.current_chord_gap_range()
            if gap is None:
                self.set_gap_analysis(None)
                return
            start, end = gap
            analysis = analyze_chord_gap(
                source_notes,
                self.editor_project.chords,
                start,
                end,
                scoring_options=self.chord_scoring_options(),
            )
            self.set_gap_analysis(analysis)

        def current_chord_gap_range(self) -> tuple[float, float] | None:
            if self.editor_project is None:
                return None
            selection = self.timeline.selection_range()
            if selection is not None:
                start, end = selection
                if end - start >= 0.05:
                    return start, end
                return None
            position = self.timeline.position
            sorted_chords = sorted(self.editor_project.chords, key=lambda chord: (chord.start, chord.end))
            for chord in sorted_chords:
                if chord.start <= position < chord.end:
                    return None
            previous = max(
                (chord for chord in sorted_chords if chord.end <= position),
                key=lambda chord: chord.end,
                default=None,
            )
            next_chord = min(
                (chord for chord in sorted_chords if chord.start >= position),
                key=lambda chord: chord.start,
                default=None,
            )
            start = previous.end if previous is not None else 0.0
            end = next_chord.start if next_chord is not None else self.editor_project.duration
            if end - start < 0.05:
                return None
            return start, end

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
            self.refresh_current_harmony(self.timeline.position)

        def handle_notation_spelling_changed(self, *_args) -> None:
            self.timeline.set_note_name_formatter(self.display_note_name)
            self.refresh_current_harmony(self.timeline.position)

        def refresh_current_harmony(self, seconds: float) -> None:
            if self.editor_project is None:
                self.current_chord.setText("Harmony: -")
                self.set_chord_context_text("Sample: -")
                self.chord_list.clear()
                self.refresh_chord_keyboard()
                self.set_theory_analysis(None)
                self.set_gap_analysis(None)
                self.current_harmony_context = None
                self.note_filter_list.clear()
                self.inspect_chord_button.setEnabled(False)
                return
            self.inspect_chord_button.setEnabled(True)
            context = self.chord_context_key(seconds)
            if context != self.chord_note_filter_context:
                self.chord_note_filter_context = context
                self.chord_note_overrides = {}
            source_notes = self.chord_analysis_notes()
            self.current_chord_base_weights = self.chord_base_pitch_weights(source_notes, context)
            analysis_notes = self.filtered_chord_analysis_notes(source_notes, context)
            sample_text = self.chord_sample_text(source_notes)
            scoring_options = self.chord_scoring_options()
            selection = self.timeline.selection_range()
            if selection is not None:
                start, end = selection
                required, excluded = self.chord_note_constraints()
                analysis = analyze_chord_region(
                    analysis_notes,
                    start,
                    end,
                    required_pitch_classes=required,
                    excluded_pitch_classes=excluded,
                    scoring_options=scoring_options,
                )
                self.refresh_current_theory(source_notes, seconds)
                chord = self.display_chord(analysis.label)
                self.current_chord.setText(
                    f"Selection: {chord}  (score {analysis.confidence:.0%})  "
                    f"{format_time(start)} - {format_time(end)}"
                )
                self._set_chord_candidates(analysis)
                self.refresh_current_gap_suggestions(source_notes)
                self.update_harmony_context("selection", source_notes, analysis_notes, analysis)
                self.populate_note_filter_list(self.current_chord_base_weights)
                if analysis.note_weights:
                    note_text = ", ".join(
                        f"{self.display_weighted_note_name(name)} ({weight:.0%})"
                        for name, weight in analysis.note_weights[:12]
                    )
                    self.set_chord_context_text(f"{sample_text}\nWeighted notes: {note_text}")
                elif analysis.active_note_names:
                    note_text = ", ".join(analysis.active_note_names[:32])
                    if len(analysis.active_note_names) > 32:
                        note_text += f", +{len(analysis.active_note_names) - 32} more"
                    self.set_chord_context_text(f"{sample_text}\nNotes in selection: {note_text}")
                else:
                    self.set_chord_context_text(f"{sample_text}\nNotes in selection: -")
                return

            required, excluded = self.chord_note_constraints()
            analysis = analyze_chord_at(
                analysis_notes,
                seconds,
                required_pitch_classes=required,
                excluded_pitch_classes=excluded,
                scoring_options=scoring_options,
            )
            active_notes = active_notes_at(analysis_notes, seconds)
            self.refresh_current_theory(source_notes, seconds)
            chord = self.display_chord(analysis.label)
            self.current_chord.setText(f"Harmony: {chord}  (score {analysis.confidence:.0%})")
            self._set_chord_candidates(analysis)
            self.refresh_current_gap_suggestions(source_notes)
            self.update_harmony_context("playhead", source_notes, analysis_notes, analysis)
            self.populate_note_filter_list(self.current_chord_base_weights)
            if active_notes:
                unique_pitches = sorted({note.pitch for note in active_notes})
                shown_pitches = unique_pitches[:32]
                note_text = ", ".join(self.display_note_name(pitch) for pitch in shown_pitches)
                if len(unique_pitches) > len(shown_pitches):
                    note_text += f", +{len(unique_pitches) - len(shown_pitches)} more"
                self.set_chord_context_text(f"{sample_text}\nNotes: {note_text}")
            else:
                self.set_chord_context_text(f"{sample_text}\nNotes: -")

        def update_harmony_context(
            self,
            mode: str,
            source_notes: list[NoteEvent],
            analysis_notes: list[NoteEvent],
            chord_analysis: ChordAnalysis,
        ) -> None:
            self.current_harmony_context = HarmonyContext(
                mode=mode,
                sampled_tracks=tuple(self.chord_analysis_track_names()),
                source_note_count=len(source_notes),
                analyzed_note_count=len(analysis_notes),
                chord_analysis=chord_analysis,
                theory_analysis=self.current_theory_analysis,
                gap_analysis=self.current_chord_gap_analysis,
            )

        def chord_context_key(self, seconds: float):
            return inspector_harmony_context_key(seconds, self.timeline.selection_range())

        def chord_analysis_notes(self) -> list[NoteEvent]:
            return selected_chord_analysis_notes(
                self.editor_project,
                self.selected_chord_analysis_tracks(),
            )

        def chord_sample_text(self, notes: list[NoteEvent]) -> str:
            if self.editor_project is None:
                return "Sample: -"
            return inspector_chord_sample_text(self.chord_analysis_track_names(), len(notes))

        def chord_analysis_track_names(self) -> list[str]:
            return inspector_chord_analysis_track_names(
                self.editor_project,
                self.selected_chord_analysis_tracks(),
            )

        def selected_chord_analysis_tracks(self) -> set[str] | None:
            if not self.track_analysis_checks:
                return None
            return {
                stem_name
                for stem_name, checkbox in self.track_analysis_checks.items()
                if checkbox.isChecked()
            }

        def chord_base_pitch_weights(self, notes: list[NoteEvent], context) -> dict[int, float]:
            return inspector_chord_base_pitch_weights(notes, context)

        def filtered_chord_analysis_notes(self, notes: list[NoteEvent], context) -> list[NoteEvent]:
            _required, excluded_pitch_classes = self.chord_note_constraints()
            return inspector_filtered_chord_analysis_notes(notes, excluded_pitch_classes)

        def chord_note_constraints(self) -> tuple[set[int], set[int]]:
            return inspector_chord_note_constraints(self.chord_note_overrides)

        def populate_note_filter_list(self, weights: dict[int, float]) -> None:
            harmony_panel.populate_note_filter_list(self, weights)

        def handle_chord_note_filter_changed(self, item) -> None:
            if self.updating_chord_note_filter:
                return
            pitch_class = item.data(Qt.UserRole)
            if pitch_class is None:
                return
            pitch_class = int(pitch_class)
            state = {
                Qt.Unchecked: "exclude",
                Qt.PartiallyChecked: "auto",
                Qt.Checked: "force",
            }.get(item.checkState(), "auto")
            if state == "auto":
                self.chord_note_overrides.pop(pitch_class, None)
            else:
                self.chord_note_overrides[pitch_class] = state
            self.refresh_current_harmony(self.timeline.position)

        def reset_chord_note_filter(self) -> None:
            self.chord_note_overrides = {}
            self.refresh_current_harmony(self.timeline.position)

        def inspect_current_chord_analysis(self) -> None:
            if self.editor_project is None:
                return
            report = self.current_chord_analysis_report()
            dialog = QDialog(self)
            dialog.setWindowTitle("Harmony Inspector Calculation")
            layout = QVBoxLayout()
            text = QTextEdit()
            text.setReadOnly(True)
            text.setPlainText(report)
            layout.addWidget(text)
            close_button = QPushButton("Close")
            close_button.clicked.connect(dialog.accept)
            button_row = QHBoxLayout()
            button_row.addStretch(1)
            button_row.addWidget(close_button)
            layout.addLayout(button_row)
            dialog.setLayout(layout)
            dialog.resize(820, 680)
            dialog.exec()

        def inspect_current_theory_analysis(self) -> None:
            if self.current_theory_analysis is None:
                return
            dialog = QDialog(self)
            dialog.setWindowTitle("Theory Inspector Calculation")
            layout = QVBoxLayout()
            text = QTextEdit()
            text.setReadOnly(True)
            text.setPlainText(theory_analysis_report(self.current_theory_analysis))
            layout.addWidget(text)
            close_button = QPushButton("Close")
            close_button.clicked.connect(dialog.accept)
            button_row = QHBoxLayout()
            button_row.addStretch(1)
            button_row.addWidget(close_button)
            layout.addLayout(button_row)
            dialog.setLayout(layout)
            dialog.resize(820, 680)
            dialog.exec()

        def inspect_current_gap_suggestions(self) -> None:
            if self.current_chord_gap_analysis is None:
                return
            dialog = QDialog(self)
            dialog.setWindowTitle("Chord Gap Suggestions")
            layout = QVBoxLayout()
            text = QTextEdit()
            text.setReadOnly(True)
            text.setPlainText(chord_gap_report(self.current_chord_gap_analysis))
            layout.addWidget(text)
            close_button = QPushButton("Close")
            close_button.clicked.connect(dialog.accept)
            button_row = QHBoxLayout()
            button_row.addStretch(1)
            button_row.addWidget(close_button)
            layout.addLayout(button_row)
            dialog.setLayout(layout)
            dialog.resize(820, 680)
            dialog.exec()

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

        def current_chord_analysis_report(self) -> str:
            return build_chord_analysis_report(self)

        def _set_chord_candidates(self, analysis) -> None:
            harmony_panel.set_chord_candidates(self, analysis)

        def select_first_chord_candidate(self) -> None:
            harmony_panel.select_first_chord_candidate(self)

        def handle_chord_selection_changed(self, *_args) -> None:
            self.refresh_chord_actions()
            self.refresh_chord_keyboard()

        def refresh_chord_keyboard(self) -> None:
            harmony_panel.refresh_chord_keyboard(self)

        def active_chord_track_region(self) -> ChordRegion | None:
            return harmony_panel.active_chord_track_region(self)

        def _candidate_notes_text(self, analysis, label: str) -> str:
            return harmony_panel.candidate_notes_text(self, analysis, label)

        def _partial_candidate_notes_text(self, analysis, label: str) -> str:
            return harmony_panel.partial_candidate_notes_text(self, analysis, label)

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
            if self.editor_project is None or self.current_result is None:
                return
            selection = self.timeline.selection_range()
            item = self.chord_list.currentItem()
            if selection is None or item is None:
                return
            label = item.data(Qt.UserRole)
            confidence = float(item.data(Qt.UserRole + 1) or 1.0)
            if not label:
                return
            start, end = selection
            manual = ChordRegion(start=start, end=end, label=label, confidence=confidence)
            self.insert_manual_chord(manual)
            self.refresh_editor_project_from_chord_edits(manual)
            self.statusBar().showMessage(
                f"Assigned {self.display_chord(label)} to {format_time(start)} - {format_time(end)}.",
                5000,
            )

        def insert_manual_chord(self, chord: ChordRegion) -> None:
            self.manual_chords = [
                existing
                for existing in self.manual_chords
                if existing.end <= chord.start or existing.start >= chord.end
            ]
            self.removed_chord_ranges = merge_chord_ranges(
                [*self.removed_chord_ranges, (chord.start, chord.end)]
            )
            self.manual_chords.append(chord)
            self.manual_chords.sort(key=lambda item: (item.start, item.end, item.label))

        def edit_timeline_chord(self, original: ChordRegion, edited: ChordRegion) -> None:
            self.removed_chord_ranges = merge_chord_ranges(
                [*self.removed_chord_ranges, (original.start, original.end), (edited.start, edited.end)]
            )
            self.manual_chords = [chord for chord in self.manual_chords if chord != original]
            self.insert_manual_chord(edited)
            self.refresh_editor_project_from_chord_edits(edited)
            self.statusBar().showMessage(
                f"Moved {self.display_chord(edited.label)} to {format_time(edited.start)} - {format_time(edited.end)}.",
                5000,
            )

        def delete_timeline_chord(self, chord: ChordRegion) -> None:
            self.removed_chord_ranges = merge_chord_ranges(
                [*self.removed_chord_ranges, (chord.start, chord.end)]
            )
            self.manual_chords = [manual for manual in self.manual_chords if manual != chord]
            self.refresh_editor_project_from_chord_edits(None)
            self.statusBar().showMessage(f"Deleted {self.display_chord(chord.label)}.", 4000)

        def show_timeline_chord_status(self, chord: ChordRegion | None) -> None:
            if chord is None:
                self.refresh_chord_keyboard()
                return
            self.refresh_chord_keyboard()
            self.statusBar().showMessage(
                f"Selected {self.display_chord(chord.label)}: drag middle to move, drag edges to resize, Delete removes it.",
                6000,
            )

        def refresh_visible_tracks(self) -> None:
            visible = {
                stem_name
                for stem_name, checkbox in self.track_visibility_checks.items()
                if checkbox.isChecked()
            }
            self.timeline.set_visible_tracks(visible)
            self.refresh_current_harmony(self.timeline.position)
            self.save_editor_state()

        def show_all_timeline_tracks(self) -> None:
            for checkbox in self.track_visibility_checks.values():
                checkbox.blockSignals(True)
                checkbox.setChecked(True)
                checkbox.blockSignals(False)
            self.refresh_visible_tracks()

        def save_editor_state(self) -> bool:
            if self.current_result is None or self.editor_project is None:
                return False
            if self.editor_save_timer.isActive():
                self.editor_save_timer.stop()
            snapshot = build_editor_state_snapshot(
                track_visibility_checks=self.track_visibility_checks,
                track_analysis_checks=self.track_analysis_checks,
                track_audio_checks=self.track_audio_checks,
                track_audio_sliders=self.track_audio_sliders,
                track_midi_checks=self.track_midi_checks,
                track_midi_sliders=self.track_midi_sliders,
                notation_spelling=self.selected_notation_preference(),
                playhead_seconds=self.timeline.position,
                manual_chords=self.manual_chords,
                removed_chord_ranges=self.removed_chord_ranges,
            )
            try:
                save_editor_state_snapshot(self.current_result, snapshot)
            except Exception as exc:
                self.logger.exception("Could not save editor state")
                self.statusBar().showMessage(f"Could not save project state: {exc}", 6000)
                return False
            return True

        def request_editor_state_save(self, delay_ms: int = 750) -> None:
            if self.current_result is None or self.editor_project is None:
                return
            self.editor_save_timer.start(delay_ms)

        def reset_stage_state(self, _path: Path | None = None) -> None:
            self.stop_transport()
            self.invalidate_worker_token()
            self.editor_load_token += 1
            self.editor_load_activity_tokens.clear()
            self.midi_preview_token += 1
            self.midi_preview_workers.clear()
            if _path is None:
                self.drop_zone.reset_prompt()
            self.current_result = None
            self.current_stems = []
            self.current_input_stem = None
            self.base_editor_project = None
            self.editor_project = None
            self.manual_chords = []
            self.removed_chord_ranges = []
            self.chord_note_overrides = {}
            self.chord_note_filter_context = None
            self.current_chord_base_weights = {}
            self.current_harmony_context = None
            self.current_theory_analysis = None
            self.current_chord_gap_analysis = None
            self.notation_spelling.blockSignals(True)
            self.notation_spelling.setCurrentIndex(0)
            self.notation_spelling.blockSignals(False)
            self.rendering_midi_previews.clear()
            self.clear_transport_players()
            self.track_audio_checks.clear()
            self.track_audio_sliders.clear()
            self.track_midi_checks.clear()
            self.track_midi_sliders.clear()
            self.track_analysis_checks.clear()
            self.track_control_panels.clear()
            self.track_control_detail_rows.clear()
            self.track_control_top_spacer = None
            self.track_control_bottom_spacer = None
            self.hidden_track_status = None
            self.latest_output_dir = None
            self.run_midi.setEnabled(False)
            self.separation_status.setText("Not run yet.")
            self.midi_status.setText("Run the full pipeline first, then MIDI can be rerun without separating again.")
            self.editor_summary.setText("Run separation + MIDI to build an editor timeline.")
            self.timeline_slider.setRange(0, 0)
            self.timeline_slider.setEnabled(False)
            self.fit_song_button.setEnabled(False)
            self.inspect_chord_button.setEnabled(False)
            self.inspect_theory_button.setEnabled(False)
            self.use_gap_suggestion_button.setEnabled(False)
            self.inspect_gap_suggestion_button.setEnabled(False)
            self.editor_position.setText(format_time(0))
            self.current_chord.setText("Harmony: -")
            self.set_chord_context_text("Sample: -")
            self.set_theory_analysis(None)
            self.set_gap_analysis(None)
            self.reset_activity("Ready for new audio")
            self.track_list.clear()
            self.note_filter_list.clear()
            self.track_visibility_checks.clear()
            self.track_note_counts.clear()
            self.editor_track_visibility = {}
            _clear_layout(self.playback_controls)
            self.chord_list.clear()
            self.refresh_chord_keyboard()
            self.timeline.set_project(None)

        def set_processing_state(self, busy: bool) -> None:
            self.drop_zone.setEnabled(not busy)
            self.run_full.setEnabled(not busy)
            self.run_midi.setEnabled((not busy) and self.current_result is not None)
            self.stem.setEnabled(not busy)
            self.bs_device.setEnabled(not busy)
            self.generate_midi.setEnabled(not busy)
            for checkbox in self.midi_stem_checks.values():
                checkbox.setEnabled(not busy and self.generate_midi.isChecked())
            for widget in [
                self.onset_threshold,
                self.frame_threshold,
                self.minimum_note_length,
                self.minimum_frequency,
                self.maximum_frequency,
                self.midi_tempo,
                self.melodia_trick,
                self.multiple_pitch_bends,
                self.save_notes,
                self.save_model_outputs,
                self.sonify_midi,
                self.sonification_samplerate,
                self.create_zip,
                self.open_when_done,
            ]:
                widget.setEnabled(not busy)
            if not busy:
                self.refresh_midi_stem_checks()

        def selected_model_key(self) -> str:
            return "bs_roformer_sw"

        def selected_separation_options(self) -> SeparationOptions:
            return SeparationOptions(
                model_key=self.selected_model_key(),
                selected_stem=self.stem.currentData(),
                device=self.bs_device.currentData(),
            )

        def selected_midi_options(self) -> MidiOptions:
            return MidiOptions(
                onset_threshold=self.onset_threshold.value(),
                frame_threshold=self.frame_threshold.value(),
                minimum_note_length=self.minimum_note_length.value(),
                minimum_frequency=optional_frequency(self.minimum_frequency.value()),
                maximum_frequency=optional_frequency(self.maximum_frequency.value()),
                multiple_pitch_bends=self.multiple_pitch_bends.isChecked(),
                melodia_trick=self.melodia_trick.isChecked(),
                midi_tempo=self.midi_tempo.value(),
                save_notes=self.save_notes.isChecked(),
                save_model_outputs=self.save_model_outputs.isChecked(),
                sonify_midi=self.sonify_midi.isChecked(),
                sonification_samplerate=self.sonification_samplerate.value(),
            )

        def selected_midi_stems(self) -> set[str]:
            if not self.generate_midi.isChecked():
                return set()
            return {
                stem_name
                for stem_name, checkbox in self.midi_stem_checks.items()
                if checkbox.isChecked()
            }

        def refresh_midi_stem_checks(self, *_args) -> None:
            choice = model_choice(self.selected_model_key())
            saved_stem = self.stem.currentData()
            previous = {stem: checkbox.isChecked() for stem, checkbox in self.midi_stem_checks.items()}
            self.midi_stem_checks.clear()
            _clear_layout(self.midi_stems_layout)

            for index, stem_name in enumerate(choice.stems):
                checkbox = QCheckBox(stem_name)
                checkbox.setChecked(previous.get(stem_name, default_midi_checked(stem_name)))
                can_run = self.generate_midi.isChecked() and (saved_stem is None or stem_name == saved_stem)
                checkbox.setEnabled(can_run)
                if saved_stem is not None and stem_name != saved_stem:
                    checkbox.setChecked(False)
                    checkbox.setToolTip("This stem is not being saved, so it cannot be analysed.")
                elif stem_name.lower() == "drums":
                    checkbox.setToolTip("Off by default because Basic Pitch is not a drum transcription model.")
                else:
                    checkbox.setToolTip("Run Basic Pitch on this separated stem.")
                self.midi_stem_checks[stem_name] = checkbox
                self.midi_stems_layout.addWidget(checkbox, index // 2, index % 2)

        def refresh_model_details(self, *_args) -> None:
            choice = model_choice(self.selected_model_key())

            self.stem.blockSignals(True)
            self.stem.clear()
            self.stem.addItem("All stems from this model", None)
            for stem_name in choice.stems:
                self.stem.addItem(stem_name, stem_name)
            self.stem.blockSignals(False)
            self.refresh_midi_stem_checks()

            torch = torch_status()
            ort = onnxruntime_status()
            self.model_title.setText(choice.label)
            self.model_summary.setText(choice.summary)
            self.model_facts.setText(
                f"Best for: {choice.best_for}\n"
                f"Creates: {', '.join(choice.stems)}\n"
                f"Evidence: {choice.score_summary}"
            )
            self.model_runtime.setText(
                f"Separation: {choice.source} on {device_label(self.bs_device.currentData(), torch.cuda_available)}. "
                f"MIDI: Spotify Basic Pitch ONNX on {'ONNX CUDA' if ort.has_cuda else 'ONNX CPU'}."
            )
            self.model_backend_detail.setText(
                f"BS-RoFormer: {choice.native_model_id}\n"
                f"Weights: {choice.filename or 'provided by registry'}\n"
                f"Config: {choice.config_filename or 'provided by registry'}\n"
                f"Calls: bs_roformer.inference.proc_folder -> basic_pitch.inference.predict_and_save"
            )

        def open_latest_output(self) -> None:
            target = self.latest_output_dir or Path(self.output_dir.text())
            self.open_folder_path(target, "output folder")

        def open_logs_folder(self) -> None:
            self.open_folder_path(logs_dir(), "logs folder")

        def open_folder_path(self, target: Path, label: str) -> None:
            try:
                opened = open_folder(target)
            except Exception as exc:
                self.logger.exception("Could not open %s: %s", label, target)
                self.append_log(f"Could not open {label}: {exc}")
                self.statusBar().showMessage(f"Could not open {label}. See logs for details.", 6000)
                return
            self.statusBar().showMessage(f"Opened {label}: {opened}", 3000)

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

    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    app = QApplication([])
    window = MainWindow()
    window.show()
    smoke_mode = os.environ.get("PITCHSTEMS_GUI_SMOKE")
    if smoke_mode in {"startup", "project"}:
        from pitchstems.gui_smoke import run_project_smoke, run_startup_smoke

        def run_smoke_and_exit() -> None:
            try:
                run_startup_smoke(window)
                if smoke_mode == "project":
                    run_project_smoke(window)
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
