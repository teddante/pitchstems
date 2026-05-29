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
    chord_tones_for_label,
    display_chord_label,
    midi_velocity_energy,
    midi_note_name,
)
from pitchstems.editor_loader import EditorLoadResult, apply_chord_edits, build_editor_load_result
from pitchstems.editor_state import (
    build_editor_state_snapshot,
    save_editor_state_snapshot,
)
from pitchstems.file_opening import open_folder
from pitchstems.midi_preview import render_midi_preview, render_note_preview
from pitchstems.model_catalog import model_choice
from pitchstems.notation import pitch_class_for_name, pitch_class_name
from pitchstems.pipeline import PipelineResult, process_audio_file, process_midi_from_stems
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
from pitchstems.gui_options import default_midi_checked, device_label, optional_frequency
from pitchstems.gui_track_controls import (
    track_control_panel_height,
    track_control_visibility,
)
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
class FullRunRequest:
    input_path: Path
    output_root: Path
    separation_options: SeparationOptions
    generate_midi: bool
    midi_options: MidiOptions
    midi_stems: set[str]
    create_zip: bool


@dataclass(frozen=True)
class MidiRunRequest:
    result: PipelineResult
    input_stem: str
    stems: list[StemResult]
    midi_options: MidiOptions
    midi_stems: set[str]
    create_zip: bool


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
            QGroupBox,
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
            self.midi_preview_workers: dict[tuple[Path, str], threading.Thread] = {}
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
            self.current_chord.setFixedWidth(320)
            self.current_chord.setStyleSheet("font-weight: 700; color: #4c1d95;")
            self.chord_context = QLabel("Sample: -")
            self.chord_context.setWordWrap(True)
            self.chord_context.setFixedHeight(74)
            self.chord_context.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            self.chord_context.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.chord_context.setStyleSheet("color: #475569;")
            self.note_filter_list = QListWidget()
            self.note_filter_list.setFixedHeight(150)
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
            self.playback_scroll.setFixedWidth(286)
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
            self.theory_context.setFixedHeight(54)
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

            output_row = QHBoxLayout()
            output_row.setSpacing(10)
            output_row.addWidget(QLabel("Output"))
            output_row.addWidget(self.output_dir, 1)

            separation_panel = QVBoxLayout()
            separation_panel.setSpacing(8)
            separation_panel.addWidget(_section_label("Separation stage"))
            intro = QLabel("PitchStems uses one stem model: BS-RoFormer SW six-stem. The checkpoint and YAML config come from the native `bs-roformer-infer` registry.")
            intro.setWordWrap(True)
            intro.setStyleSheet("color: #4b5563;")
            separation_panel.addWidget(intro)
            separation_panel.addWidget(self.workflow_note)
            separation_card = QGroupBox("BS-RoFormer SW six-stem")
            separation_card_layout = QVBoxLayout()
            separation_card_layout.setSpacing(8)
            separation_card_layout.addWidget(self.model_summary)
            separation_card_layout.addWidget(self.model_facts)
            separation_card_layout.addWidget(self.audio_prep)
            separation_card_layout.addWidget(self.separation_status)
            separation_card.setLayout(separation_card_layout)
            separation_panel.addWidget(separation_card)
            midi_stage_card = QGroupBox("MIDI stage")
            midi_stage_layout = QVBoxLayout()
            midi_stage_layout.setSpacing(8)
            midi_stage_layout.addWidget(self.midi_status)
            midi_stage_card.setLayout(midi_stage_layout)
            separation_panel.addWidget(midi_stage_card)
            separation_panel.addStretch(1)

            selected_panel = QVBoxLayout()
            selected_panel.setSpacing(8)
            selected_panel.addWidget(_section_label("Controls"))

            runtime_group = QGroupBox("BS-RoFormer runtime")
            runtime_layout = QVBoxLayout()
            runtime_layout.setSpacing(8)
            runtime_layout.addWidget(self.bs_device)
            runtime_layout.addWidget(self.bs_device_help)
            runtime_group.setLayout(runtime_layout)

            backend_group = QGroupBox("Native backend")
            backend_layout = QVBoxLayout()
            backend_layout.setSpacing(6)
            backend_layout.addWidget(self.model_runtime)
            backend_layout.addWidget(self.model_backend_detail)
            backend_group.setLayout(backend_layout)

            stem_group = QGroupBox("Files to save")
            stem_layout = QVBoxLayout()
            stem_layout.setContentsMargins(10, 8, 10, 8)
            stem_layout.addWidget(self.stem)
            stem_group.setLayout(stem_layout)

            midi_group = QGroupBox("MIDI")
            midi_layout = QVBoxLayout()
            midi_layout.setSpacing(8)
            midi_layout.setContentsMargins(10, 8, 10, 8)
            midi_layout.addWidget(self.generate_midi)
            midi_layout.addLayout(self.midi_stems_layout)
            midi_layout.addWidget(self.midi_help)
            midi_group.setLayout(midi_layout)

            midi_settings_tab = QWidget()
            midi_settings_layout = QVBoxLayout()
            midi_settings_layout.setContentsMargins(8, 8, 8, 8)
            midi_settings_layout.setSpacing(6)
            midi_settings_intro = QLabel("These are Basic Pitch's official `predict_and_save` parameters. Defaults shown here are Basic Pitch defaults.")
            midi_settings_intro.setWordWrap(True)
            midi_settings_intro.setStyleSheet("color: #4b5563;")
            midi_settings_layout.addWidget(midi_settings_intro)
            midi_settings_hint = QLabel("Higher thresholds are stricter and usually create fewer notes. Frequency limits filter the MIDI note range after prediction.")
            midi_settings_hint.setWordWrap(True)
            midi_settings_hint.setStyleSheet("color: #4b5563;")
            midi_settings_layout.addWidget(midi_settings_hint)
            midi_grid = QGridLayout()
            midi_grid.setHorizontalSpacing(10)
            midi_grid.setVerticalSpacing(5)
            _grid_control(midi_grid, 0, 0, "Note starts", "default 0.50", self.onset_threshold)
            _grid_control(midi_grid, 0, 1, "Sustained notes", "default 0.30", self.frame_threshold)
            _grid_control(midi_grid, 1, 0, "Minimum note", "default 127.7 ms", self.minimum_note_length)
            _grid_control(midi_grid, 1, 1, "MIDI tempo", "default 120", self.midi_tempo)
            _grid_control(midi_grid, 2, 0, "Lowest note", "default off", self.minimum_frequency)
            _grid_control(midi_grid, 2, 1, "Highest note", "default off", self.maximum_frequency)
            _grid_control(midi_grid, 3, 0, "Check audio rate", "default 44100", self.sonification_samplerate)
            midi_settings_layout.addLayout(midi_grid)

            midi_checks = QGridLayout()
            midi_checks.setHorizontalSpacing(10)
            midi_checks.setVerticalSpacing(3)
            midi_checks.addWidget(self.melodia_trick, 0, 0)
            midi_checks.addWidget(self.multiple_pitch_bends, 0, 1)
            midi_checks.addWidget(self.save_notes, 1, 0)
            midi_checks.addWidget(self.save_model_outputs, 1, 1)
            midi_checks.addWidget(self.sonify_midi, 2, 0)
            midi_settings_layout.addLayout(midi_checks)
            midi_settings_layout.addStretch(1)
            midi_settings_tab.setLayout(midi_settings_layout)

            export_group = QGroupBox("Export")
            export_layout = QVBoxLayout()
            export_layout.setSpacing(8)
            export_layout.setContentsMargins(10, 8, 10, 8)
            export_layout.addWidget(self.create_zip)
            export_layout.addWidget(self.open_when_done)
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

            self.processing_tabs.addTab(midi_settings_tab, "Basic Pitch")
            self.processing_tabs.addTab(runtime_tab, "Runtime")

            selected_panel.addWidget(stem_group)
            selected_panel.addWidget(midi_group)
            selected_panel.addWidget(self.processing_tabs, 1)
            selected_panel.addStretch(1)

            main_row = QHBoxLayout()
            main_row.setSpacing(16)
            main_row.addLayout(separation_panel, 3)
            main_row.addLayout(selected_panel, 2)

            action_row = QHBoxLayout()
            action_row.addStretch(1)
            action_row.addWidget(self.run_midi)
            action_row.addWidget(self.run_full)

            pipeline_layout = QVBoxLayout()
            pipeline_layout.setContentsMargins(12, 12, 12, 12)
            pipeline_layout.setSpacing(10)
            pipeline_layout.addWidget(self.drop_zone)
            pipeline_layout.addLayout(output_row)
            pipeline_layout.addLayout(main_row, 1)
            pipeline_layout.addLayout(action_row)
            pipeline_layout.addWidget(self.log, 1)
            pipeline_page = QWidget()
            pipeline_page.setLayout(pipeline_layout)

            editor_page = QWidget()
            editor_layout = QVBoxLayout()
            editor_layout.setContentsMargins(12, 12, 12, 12)
            editor_layout.setSpacing(10)
            editor_layout.addWidget(self.editor_summary)

            transport_row = QHBoxLayout()
            transport_row.setSpacing(8)
            transport_row.addWidget(self.play_button)
            transport_row.addWidget(self.stop_button)
            transport_row.addWidget(self.fit_song_button)
            transport_row.addWidget(QLabel("Position"))
            transport_row.addWidget(self.editor_position)
            transport_row.addWidget(self.current_chord)
            transport_row.addStretch(1)
            editor_layout.addLayout(transport_row)

            editor_body = QHBoxLayout()
            editor_body.setSpacing(10)
            editor_side_panel = QWidget()
            editor_side_panel.setFixedWidth(330)
            editor_side = QVBoxLayout()
            editor_side.setContentsMargins(0, 0, 0, 0)
            editor_side.setSpacing(8)
            editor_side.addWidget(_section_label("Harmony Inspector"))
            editor_side.addWidget(self.notation_spelling)
            editor_side.addWidget(self.chord_context)
            editor_side.addWidget(self.chord_detector_help)
            evidence_floor_row = QHBoxLayout()
            evidence_floor_row.setSpacing(8)
            evidence_floor_row.addWidget(self.min_note_evidence_label)
            evidence_floor_row.addWidget(self.min_note_evidence_slider, 1)
            editor_side.addLayout(evidence_floor_row)
            editor_side.addWidget(_section_label("Manual Note Overrides"))
            editor_side.addWidget(self.note_filter_help)
            editor_side.addWidget(self.note_filter_list)
            chord_action_grid = QGridLayout()
            chord_action_grid.setHorizontalSpacing(6)
            chord_action_grid.setVerticalSpacing(4)
            chord_action_grid.addWidget(self.preview_chord_button, 0, 0)
            chord_action_grid.addWidget(self.use_chord_button, 0, 1)
            chord_action_grid.addWidget(self.reset_note_filter_button, 1, 0)
            chord_action_grid.addWidget(self.inspect_chord_button, 1, 1)
            editor_side.addLayout(chord_action_grid)
            editor_side.addWidget(self.piano_chord_view)
            editor_side.addWidget(self.chord_list, 1)
            theory_header = QHBoxLayout()
            theory_header.setSpacing(6)
            theory_header.addWidget(_section_label("Theory Inspector"))
            theory_header.addWidget(self.inspect_theory_button)
            editor_side.addLayout(theory_header)
            editor_side.addWidget(self.theory_context)
            editor_side.addWidget(self.theory_list, 1)
            gap_header = QHBoxLayout()
            gap_header.setSpacing(6)
            gap_header.addWidget(_section_label("Gap Suggestions"))
            gap_header.addWidget(self.use_gap_suggestion_button)
            gap_header.addWidget(self.inspect_gap_suggestion_button)
            editor_side.addLayout(gap_header)
            editor_side.addWidget(self.gap_suggestion_list, 1)
            editor_side_panel.setLayout(editor_side)
            track_mix_panel = QWidget()
            track_mix_panel.setFixedWidth(292)
            track_mix_layout = QVBoxLayout()
            track_mix_layout.setContentsMargins(0, 0, 0, 0)
            track_mix_layout.setSpacing(0)
            track_mix_layout.addWidget(self.playback_scroll, 1)
            track_mix_panel.setLayout(track_mix_layout)
            editor_body.addWidget(editor_side_panel)
            editor_body.addWidget(track_mix_panel)
            editor_body.addWidget(self.timeline, 1)
            editor_layout.addLayout(editor_body, 1)
            editor_page.setLayout(editor_layout)

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
            if self.worker and self.worker.is_alive():
                return
            if not self.drop_zone.path:
                self.append_log("Drop an audio file first.")
                return
            midi_stems = self.selected_midi_stems()
            request = FullRunRequest(
                input_path=self.drop_zone.path,
                output_root=Path(self.output_dir.text()),
                separation_options=self.selected_separation_options(),
                generate_midi=self.generate_midi.isChecked() and bool(midi_stems),
                midi_options=self.selected_midi_options(),
                midi_stems=midi_stems,
                create_zip=self.create_zip.isChecked(),
            )

            self.set_processing_state(True)
            self.begin_activity("Running separation + MIDI...")
            self.append_log("Starting separation + MIDI pipeline...")
            token = self.start_worker_token()
            self.worker = threading.Thread(target=self.run_full_pipeline, args=(token, request), daemon=True)
            self.worker.start()

        def start_midi_processing(self) -> None:
            if self.worker and self.worker.is_alive():
                return
            if not self.current_result or not self.current_stems or not self.current_input_stem:
                self.append_log("Run separation first. Then MIDI can be rerun from those stems.")
                return
            request = MidiRunRequest(
                result=self.current_result,
                input_stem=self.current_input_stem,
                stems=list(self.current_stems),
                midi_options=self.selected_midi_options(),
                midi_stems=self.selected_midi_stems(),
                create_zip=self.create_zip.isChecked(),
            )

            self.set_processing_state(True)
            self.begin_activity("Rerunning MIDI...")
            self.append_log("Rerunning MIDI from existing stems...")
            token = self.start_worker_token()
            self.worker = threading.Thread(target=self.run_midi_stage, args=(token, request), daemon=True)
            self.worker.start()

        def start_worker_token(self) -> int:
            self.worker_token += 1
            self.active_worker_token = self.worker_token
            return self.worker_token

        def invalidate_worker_token(self) -> None:
            had_active_worker = self.active_worker_token is not None
            self.worker_token += 1
            self.active_worker_token = None
            if had_active_worker:
                self.set_processing_state(False)

        def run_full_pipeline(self, token: int, request: FullRunRequest) -> None:
            try:
                self.logger.info("Starting full pipeline for %s", request.input_path)
                result = process_audio_file(
                    request.input_path,
                    request.output_root,
                    separation_options=request.separation_options,
                    generate_midi=request.generate_midi,
                    midi_policy="all",
                    midi_options=request.midi_options,
                    midi_stems=request.midi_stems,
                    create_zip=request.create_zip,
                    log=lambda message: self.messages.put(("WORKER_LOG", token, message)),
                )
                self.messages.put(("RESULT", token, result))
                self.messages.put(("WORKER_LOG", token, f"Project ready: {result.project_dir}"))
            except Exception as exc:
                self.logger.exception("Full pipeline failed")
                self.messages.put(("WORKER_LOG", token, f"Error: {exc}"))
            finally:
                self.messages.put(("ENABLE_PROCESS", token))

        def run_midi_stage(self, token: int, request: MidiRunRequest) -> None:
            try:
                self.logger.info("Starting MIDI rerun for %s", request.result.project_dir)
                result = process_midi_from_stems(
                    project_dir=request.result.project_dir,
                    input_stem=request.input_stem,
                    normalized_audio=request.result.normalized_audio,
                    stems=request.stems,
                    midi_policy="all",
                    midi_options=request.midi_options,
                    midi_stems=request.midi_stems,
                    create_zip=request.create_zip,
                    log=lambda message: self.messages.put(("WORKER_LOG", token, message)),
                )
                self.messages.put(("RESULT", token, result))
                self.messages.put(("WORKER_LOG", token, f"Updated project MIDI: {result.project_dir}"))
            except Exception as exc:
                self.logger.exception("MIDI rerun failed")
                self.messages.put(("WORKER_LOG", token, f"Error: {exc}"))
            finally:
                self.messages.put(("ENABLE_PROCESS", token))

        def flush_messages(self) -> None:
            while True:
                try:
                    message = self.messages.get_nowait()
                except queue.Empty:
                    return
                if isinstance(message, tuple) and message[0] == "RESULT":
                    _kind, token, result = message
                    if self.is_active_worker_token(int(token)):
                        self.set_current_result(result)
                    else:
                        self.logger.info("Ignored stale worker result for %s", result.project_dir)
                elif isinstance(message, tuple) and message[0] == "WORKER_LOG":
                    _kind, token, text = message
                    if self.is_active_worker_token(int(token)):
                        self.append_log(str(text))
                        if text and not str(text).startswith("Tracks:"):
                            self.set_activity_message(str(text)[:120])
                    else:
                        self.logger.info("Ignored stale worker log: %s", text)
                elif isinstance(message, tuple) and message[0] == "EDITOR_LOADED":
                    _kind, token, loaded = message
                    self.finish_editor_project_load(int(token), loaded)
                elif isinstance(message, tuple) and message[0] == "EDITOR_LOAD_FAILED":
                    _kind, token, project_dir, error = message
                    self.finish_editor_project_load_failed(int(token), project_dir, error)
                elif isinstance(message, tuple) and message[0] == "MIDI_PREVIEWS":
                    _kind, token, project_dir, requested_stems, previews = message
                    for stem_name in requested_stems:
                        self.midi_preview_workers.pop((project_dir, stem_name.lower()), None)
                    if (
                        token == self.midi_preview_token
                        and self.current_result is not None
                        and self.current_result.project_dir == project_dir
                    ):
                        self.rendering_midi_previews.difference_update(requested_stems)
                        self.attach_midi_preview_players(previews)
                    else:
                        self.logger.info("Ignored stale MIDI preview render for %s", project_dir)
                elif isinstance(message, tuple) and message[0] == "MIDI_PREVIEW_FAILED":
                    _kind, token, project_dir, requested_stems, error = message
                    for stem_name in requested_stems:
                        self.midi_preview_workers.pop((project_dir, stem_name.lower()), None)
                    if (
                        token == self.midi_preview_token
                        and self.current_result is not None
                        and self.current_result.project_dir == project_dir
                    ):
                        self.rendering_midi_previews.difference_update(requested_stems)
                        self.refresh_timeline_track_summaries()
                        self.append_log(error)
                        self.end_activity("MIDI preview audio failed")
                    else:
                        self.logger.info("Ignored stale MIDI preview failure for %s: %s", project_dir, error)
                elif isinstance(message, tuple) and message[0] == "ENABLE_PROCESS":
                    _kind, token = message
                    if self.is_active_worker_token(int(token)):
                        self.active_worker_token = None
                        self.set_processing_state(False)
                        self.end_activity("Processing complete")
                    else:
                        self.logger.info("Ignored stale worker completion for token %s", token)
                elif isinstance(message, str) and message.startswith("__OUTPUT_DIR__"):
                    self.latest_output_dir = Path(message.removeprefix("__OUTPUT_DIR__"))
                    if self.open_when_done.isChecked():
                        self.open_latest_output()
                elif isinstance(message, str):
                    self.append_log(message)
                    if message and not message.startswith("Tracks:"):
                        self.set_activity_message(message[:120])
                else:
                    self.logger.warning("Ignored unknown worker message: %r", message)

        def is_active_worker_token(self, token: int) -> bool:
            return self.active_worker_token == token

        def append_log(self, message: str) -> None:
            self.logger.info(message)
            self.log.append(message)

        def set_current_result(self, result: PipelineResult, open_output: bool = True) -> None:
            self.logger.info("Setting current result: %s", result.project_dir)
            self.set_activity_message("Loading result...")
            self.editor_load_token += 1
            self.current_result = result
            self.midi_preview_token += 1
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
            playhead_seconds = float(editor_state.get("playhead_seconds", 0.0) or 0.0)
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
            _clear_layout(self.playback_controls)
            self.track_audio_checks.clear()
            self.track_audio_sliders.clear()
            self.track_midi_checks.clear()
            self.track_midi_sliders.clear()
            self.track_visibility_checks.clear()
            self.track_analysis_checks.clear()
            self.track_control_panels.clear()
            self.track_control_detail_rows.clear()
            self.track_control_top_spacer = None
            self.track_control_bottom_spacer = None
            self.hidden_track_status = None
            if self.editor_project is None:
                return

            track_visibility = self.editor_track_visibility
            analysis_enabled = editor_state.get("track_analysis_enabled", {})
            audio_enabled = editor_state.get("track_audio_enabled", {})
            audio_volume = editor_state.get("track_audio_volume", {})
            midi_enabled = editor_state.get("track_midi_enabled", {})
            midi_volume = editor_state.get("track_midi_volume", {})

            self.track_control_top_spacer = QWidget()
            self.track_control_top_spacer.setFixedHeight(int(self.timeline.chord_height))
            top_layout = QVBoxLayout()
            top_layout.setContentsMargins(8, 6, 8, 6)
            top_layout.setSpacing(4)
            top_title_row = QHBoxLayout()
            top_title_row.setContentsMargins(0, 0, 0, 0)
            top_title_row.setSpacing(6)
            top_title = QLabel("Tracks & Mix")
            top_title.setStyleSheet("font-weight: 700; color: #334155;")
            hidden_status = QLabel("")
            hidden_status.setStyleSheet("color: #64748b; font-size: 10px;")
            hidden_status.setToolTip("Tracks hidden with View off are removed from the timeline lanes. Use Show All to restore them.")
            show_all_button = QPushButton("Show All")
            show_all_button.setToolTip("Restore every track to the timeline.")
            show_all_button.clicked.connect(self.show_all_timeline_tracks)
            top_title_row.addWidget(top_title)
            top_title_row.addStretch(1)
            top_title_row.addWidget(hidden_status)
            top_layout.addLayout(top_title_row)
            top_layout.addWidget(show_all_button)
            self.track_control_top_spacer.setLayout(top_layout)
            self.hidden_track_status = hidden_status
            self.playback_controls.addWidget(self.track_control_top_spacer)

            for track in self.editor_project.tracks:
                note_count = self.track_note_counts.get(track.name, 0)
                track_panel = QWidget()
                track_panel.setObjectName("trackControlRow")
                track_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                track_panel.setStyleSheet(
                    """
                    QWidget#trackControlRow {
                        background: #ffffff;
                        border-bottom: 1px solid #e2e8f0;
                    }
                    QLabel, QCheckBox, QSlider {
                        border: 0;
                        background: transparent;
                    }
                    QCheckBox {
                        color: #334155;
                        font-size: 9px;
                        spacing: 2px;
                    }
                    QSlider {
                        min-height: 12px;
                        max-height: 12px;
                    }
                    """
                )
                track_layout = QVBoxLayout()
                track_layout.setContentsMargins(6, 2, 6, 2)
                track_layout.setSpacing(1)

                title_row = QHBoxLayout()
                title_row.setContentsMargins(0, 0, 0, 0)
                title_row.setSpacing(6)
                title = QLabel(track.name)
                title.setStyleSheet("font-weight: 700; color: #0f172a;")
                notes = QLabel(f"{note_count:,} notes")
                notes.setStyleSheet("color: #64748b;")
                title_row.addWidget(title)
                title_row.addStretch(1)
                title_row.addWidget(notes)
                track_layout.addLayout(title_row)

                toggle_widget = QWidget()
                toggle_row = QHBoxLayout()
                toggle_row.setContentsMargins(0, 0, 0, 0)
                toggle_row.setSpacing(6)

                show_check = QCheckBox("View")
                show_check.setChecked(track_visibility.get(track.name, True))
                show_check.setToolTip(
                    "Show this track's lane on the timeline. Turning it off hides this row too; use Show All to restore hidden tracks."
                )
                show_check.toggled.connect(lambda *_args: self.refresh_visible_tracks())
                self.track_visibility_checks[track.name] = show_check
                toggle_row.addWidget(show_check)

                analysis_check = QCheckBox("Chord")
                analysis_check.setChecked(analysis_enabled.get(track.name, track_visibility.get(track.name, True)))
                analysis_check.setToolTip("Include this track's generated MIDI notes in the Harmony Inspector sample.")
                analysis_check.toggled.connect(lambda *_args: self.refresh_current_harmony(self.timeline.position))
                analysis_check.toggled.connect(lambda *_args: self.save_editor_state())
                analysis_check.toggled.connect(lambda *_args: self.refresh_timeline_track_summaries())
                self.track_analysis_checks[track.name] = analysis_check
                toggle_row.addWidget(analysis_check)

                audio_check = QCheckBox("Audio")
                audio_check.setChecked(audio_enabled.get(track.name, True))
                audio_check.setToolTip("Play this separated stem audio in the editor transport. Does not affect chord detection.")
                audio_slider = QSlider(Qt.Horizontal)
                audio_slider.setRange(0, 100)
                audio_slider.setValue(int(audio_volume.get(track.name, 80)))
                audio_slider.setToolTip("Separated stem audio volume.")
                audio_check.toggled.connect(lambda *_args: self.refresh_playback_mix())
                audio_check.toggled.connect(lambda *_args: self.save_editor_state())
                audio_check.toggled.connect(lambda *_args: self.refresh_timeline_track_summaries())
                audio_slider.valueChanged.connect(lambda *_args: self.refresh_playback_mix())
                audio_slider.valueChanged.connect(lambda *_args: self.save_editor_state())
                audio_slider.sliderReleased.connect(lambda *_args: self.refresh_timeline_track_summaries())
                self.track_audio_checks[track.name] = audio_check
                self.track_audio_sliders[track.name] = audio_slider
                toggle_row.addWidget(audio_check)

                midi_check = QCheckBox("MIDI")
                midi_check.setChecked(midi_enabled.get(track.name, False))
                has_midi_notes = note_count > 0
                midi_check.setEnabled(has_midi_notes)
                midi_check.setToolTip("Play this stem's generated MIDI preview audio. Missing previews render only when this MIDI track is turned on.")
                midi_slider = QSlider(Qt.Horizontal)
                midi_slider.setRange(0, 100)
                midi_slider.setValue(int(midi_volume.get(track.name, 70)))
                midi_slider.setEnabled(has_midi_notes)
                midi_slider.setToolTip("MIDI preview volume.")
                midi_check.toggled.connect(
                    lambda checked, stem_name=track.name: self.handle_midi_track_toggled(stem_name, checked)
                )
                midi_slider.valueChanged.connect(lambda *_args: self.refresh_playback_mix())
                midi_slider.valueChanged.connect(lambda *_args: self.save_editor_state())
                midi_slider.sliderReleased.connect(lambda *_args: self.refresh_timeline_track_summaries())
                self.track_midi_checks[track.name] = midi_check
                self.track_midi_sliders[track.name] = midi_slider
                toggle_row.addWidget(midi_check)
                toggle_row.addStretch(1)
                toggle_widget.setLayout(toggle_row)
                track_layout.addWidget(toggle_widget)

                audio_widget = QWidget()
                slider_row = QHBoxLayout()
                slider_row.setContentsMargins(0, 0, 0, 0)
                slider_row.setSpacing(6)
                audio_label = QLabel("Audio")
                audio_label.setFixedWidth(42)
                audio_label.setStyleSheet("color: #64748b;")
                audio_label.setToolTip("Separated stem audio volume.")
                slider_row.addWidget(audio_label)
                slider_row.addWidget(audio_slider)
                audio_widget.setLayout(slider_row)
                track_layout.addWidget(audio_widget)

                midi_widget = QWidget()
                midi_slider_row = QHBoxLayout()
                midi_slider_row.setContentsMargins(0, 0, 0, 0)
                midi_slider_row.setSpacing(6)
                midi_label = QLabel("MIDI")
                midi_label.setFixedWidth(42)
                midi_label.setStyleSheet("color: #64748b;")
                midi_label.setToolTip("Generated MIDI preview volume.")
                midi_slider_row.addWidget(midi_label)
                midi_slider_row.addWidget(midi_slider)
                midi_widget.setLayout(midi_slider_row)
                track_layout.addWidget(midi_widget)
                track_panel.setLayout(track_layout)
                self.track_control_panels[track.name] = track_panel
                self.track_control_detail_rows[track.name] = (toggle_widget, audio_widget, midi_widget)
                self.playback_controls.addWidget(track_panel)
            self.track_control_bottom_spacer = QWidget()
            self.track_control_bottom_spacer.setFixedHeight(34)
            self.playback_controls.addWidget(self.track_control_bottom_spacer)
            self.sync_track_control_panel()

        def handle_midi_track_toggled(self, stem_name: str, checked: bool) -> None:
            if checked and self.current_result is not None and stem_name not in self.transport.midi_preview_paths:
                self.start_midi_preview_render(self.current_result, {stem_name})
            self.refresh_playback_mix()
            self.refresh_timeline_track_summaries()
            self.save_editor_state()

        def refresh_timeline_track_summaries(self) -> None:
            self.sync_track_control_panel()

        def sync_track_control_panel(self) -> None:
            if self.track_control_top_spacer is not None:
                self.track_control_top_spacer.setFixedHeight(int(self.timeline.chord_height))
            if self.track_control_bottom_spacer is not None:
                self.track_control_bottom_spacer.setFixedHeight(34)
            if self.editor_project is None:
                return
            hidden_tracks = [
                track.name
                for track in self.editor_project.tracks
                if self.track_visibility_checks.get(track.name)
                and not self.track_visibility_checks[track.name].isChecked()
            ]
            if self.hidden_track_status is not None:
                if hidden_tracks:
                    self.hidden_track_status.setText(f"Hidden: {len(hidden_tracks)}")
                    self.hidden_track_status.setToolTip(
                        "Hidden timeline tracks: " + ", ".join(hidden_tracks)
                    )
                else:
                    self.hidden_track_status.setText("All tracks visible")
                    self.hidden_track_status.setToolTip("No timeline tracks are hidden.")
            for track in self.editor_project.tracks:
                panel = self.track_control_panels.get(track.name)
                if panel is None:
                    continue
                visible_check = self.track_visibility_checks.get(track.name)
                is_visible = visible_check is None or visible_check.isChecked()
                panel.setVisible(is_visible)
                if not is_visible:
                    continue
                geometry = self.timeline.track_geometries.get(track.name.lower())
                height = track_control_panel_height(geometry[1] if geometry else None)
                panel.setFixedHeight(height)
                detail_rows = self.track_control_detail_rows.get(track.name)
                if detail_rows is None:
                    continue
                toggle_widget, audio_widget, midi_widget = detail_rows
                visibility = track_control_visibility(height)
                toggle_widget.setVisible(visibility.toggles)
                audio_widget.setVisible(visibility.audio_volume)
                midi_widget.setVisible(visibility.midi_volume)
            self.playback_controls_widget.adjustSize()

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
                self.midi_preview_workers[(result.project_dir, stem_name.lower())] = worker_thread
            worker_thread.start()

        def _midi_preview_worker_running(self, project_dir: Path, stem_name: str) -> bool:
            worker = self.midi_preview_workers.get((project_dir, stem_name.lower()))
            return bool(worker and worker.is_alive())

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
            self.current_chord_gap_analysis = analysis
            self.gap_suggestion_list.clear()
            if analysis is None or not analysis.suggestions:
                self.gap_suggestion_list.addItem("No chord-track gap selected or under the playhead.")
                self.refresh_gap_suggestion_actions()
                return
            self.gap_suggestion_list.addItem(
                f"Gap {format_time(analysis.start)} - {format_time(analysis.end)}"
            )
            for index, suggestion in enumerate(analysis.suggestions[:8]):
                item = QListWidgetItem(
                    f"{self.display_chord(suggestion.label)}  {suggestion.score:.0%}\n"
                    f"{suggestion.action.replace('_', ' ')} | local {suggestion.local_evidence:.0%}, "
                    f"theory {suggestion.theory_fit:.0%}, voice {suggestion.voice_leading:.0%}"
                )
                item.setData(Qt.UserRole, index)
                item.setToolTip("\n".join(suggestion.explanation))
                self.gap_suggestion_list.addItem(item)
            self.gap_suggestion_list.setCurrentRow(1)
            self.refresh_gap_suggestion_actions()

        def refresh_gap_suggestion_actions(self) -> None:
            item = self.gap_suggestion_list.currentItem()
            has_suggestion = bool(item and item.data(Qt.UserRole) is not None)
            self.use_gap_suggestion_button.setEnabled(has_suggestion)
            self.inspect_gap_suggestion_button.setEnabled(
                self.current_chord_gap_analysis is not None
                and bool(self.current_chord_gap_analysis.suggestions)
            )

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
            self.timeline.redraw()
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
            self.updating_chord_note_filter = True
            try:
                self.note_filter_list.clear()
                detected = sorted(weights, key=lambda pitch_class: (-weights[pitch_class], pitch_class))
                missing = [pitch_class for pitch_class in range(12) if pitch_class not in weights]
                for pitch_class in [*detected, *missing]:
                    state = self.chord_note_overrides.get(pitch_class, "auto")
                    if pitch_class in weights:
                        detail = f"{weights[pitch_class]:.0%}"
                    else:
                        detail = "not detected"
                    if state == "exclude":
                        detail = f"{detail}; hard excluded"
                    elif state == "force":
                        detail = "forced in"
                    label = {"exclude": "Exclude", "auto": "Auto", "force": "Force"}[state]
                    item = QListWidgetItem(f"{label} {self.display_pitch_class_name(pitch_class)}  -  {detail}")
                    item.setData(Qt.UserRole, pitch_class)
                    tristate_flag = getattr(Qt, "ItemIsUserTristate", Qt.ItemIsUserCheckable)
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable | tristate_flag)
                    check_state = {
                        "exclude": Qt.Unchecked,
                        "auto": Qt.PartiallyChecked,
                        "force": Qt.Checked,
                    }[state]
                    item.setCheckState(check_state)
                    item.setToolTip(
                        "Unchecked: Exclude any chord name containing this note.\n"
                        "Mixed: Auto, use detector evidence naturally.\n"
                        "Checked: Force chord names to contain this note."
                    )
                    self.note_filter_list.addItem(item)
            finally:
                self.updating_chord_note_filter = False

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
            source_notes = self.chord_analysis_notes()
            context = self.chord_context_key(self.timeline.position)
            self.current_chord_base_weights = self.chord_base_pitch_weights(source_notes, context)
            analysis_notes = self.filtered_chord_analysis_notes(source_notes, context)
            required, excluded = self.chord_note_constraints()
            scoring_options = self.chord_scoring_options()
            selection = self.timeline.selection_range()
            if selection is not None:
                start, end = selection
                analysis = analyze_chord_region(
                    analysis_notes,
                    start,
                    end,
                    required_pitch_classes=required,
                    excluded_pitch_classes=excluded,
                    scoring_options=scoring_options,
                )
                mode = f"Selection {format_time(start)} - {format_time(end)} ({end - start:.3f} sec)"
                evidence_rows, totals = self.chord_selection_evidence_rows(analysis_notes, start, end)
            else:
                seconds = self.timeline.position
                analysis = analyze_chord_at(
                    analysis_notes,
                    seconds,
                    required_pitch_classes=required,
                    excluded_pitch_classes=excluded,
                    scoring_options=scoring_options,
                )
                mode = f"Playhead {format_time(seconds)}"
                evidence_rows, totals = self.chord_point_evidence_rows(analysis_notes, seconds)

            lines = [
                "Harmony Inspector Calculation",
                "=" * 29,
                f"Context: {mode}",
                f"Detected chord: {self.display_chord(analysis.label)} (ranking score {analysis.confidence:.0%})",
                f"Sampled tracks: {', '.join(self.chord_analysis_track_names()) or '-'}",
                f"Source MIDI notes in sampled tracks: {len(source_notes):,}",
                f"Filtered/analyzed note events: {len(analysis_notes):,}",
                "",
                "MIDI Energy Evidence",
                "-" * 17,
                "MIDI energy model: note energy = overlap_seconds * (velocity / 127)^2",
                "Octaves and tracks: every note event contributes separately, then totals are folded by note name.",
                "Low-energy notes are kept unless the minimum note evidence slider or Manual Note Overrides remove them from naming.",
                (
                    f"Minimum note evidence: {self.min_note_evidence_slider.value()}% normalized. "
                    "Raw totals below this remain visible here but are ignored for chord naming."
                ),
                "",
                "Chord-Name Ranking",
                "-" * 18,
                "The visible percentage is a local ranking score, not a statistical probability.",
                "Display score = coverage * purity, using the MIDI evidence already shown above.",
                "Coverage asks how strongly the candidate's expected notes are present.",
                "Purity asks how much of the selected energy belongs to the candidate's notes.",
                "Automatic chord names that require a tone below visible evidence resolution are rejected.",
                "Forced notes constrain chord names without inventing MIDI energy.",
                "No naming bonuses, penalties, or user-tuned weights are applied.",
                "",
                "Manual Note Evidence Overrides",
                "-" * 30,
                f"Forced notes: {self.pitch_class_list(required)}",
                f"Excluded notes: {self.pitch_class_list(excluded)}",
                "",
                "Weighted Pitch-Class Totals",
                "-" * 27,
            ]
            if totals:
                max_total = max(totals.values())
                for pitch_class, total in sorted(totals.items(), key=lambda item: (-item[1], item[0])):
                    lines.append(f"{self.display_pitch_class_name(pitch_class):>2}: raw {total:.4f}, normalized {total / max_total:.0%}")
            else:
                lines.append("-")
            if analysis.note_weights:
                lines.extend(["", "Pitch Classes Used By Detector", "-" * 30])
                for name, weight in analysis.note_weights:
                    pitch_class = pitch_class_for_name(name)
                    shown_name = self.display_pitch_class_name(pitch_class) if pitch_class is not None else name
                    lines.append(f"{shown_name:>2}: {weight:.0%}")

            lines.extend(["", "Input Note Events", "-" * 17])
            if evidence_rows:
                lines.extend(evidence_rows[:400])
                if len(evidence_rows) > 400:
                    lines.append(f"... {len(evidence_rows) - 400} more note events")
            else:
                lines.append("-")

            lines.extend(["", "Chord Candidates And Formula Breakdown", "-" * 39])
            if analysis.candidates:
                for label, confidence in analysis.candidates:
                    notes = " - ".join(self.display_chord_tones(label)) or "-"
                    aliases = ", ".join(self.display_chord(alias) for alias in analysis.candidate_aliases.get(label, [])) or "-"
                    lines.extend(
                        [
                            "",
                            f"{self.display_chord(label)} ({confidence:.0%})",
                            f"Official tones: {notes}",
                            f"Alternate names: {aliases}",
                        ]
                    )
                    lines.extend(analysis.candidate_explanations.get(label, ["No explanation available."]))
            else:
                lines.append("No full chord candidates here.")
            if analysis.partial_candidates:
                lines.extend(["", "Partial Chord Candidates", "-" * 24])
                for label, confidence in analysis.partial_candidates:
                    notes = " - ".join(self.display_chord_tones(label)) or "-"
                    aliases = ", ".join(self.display_chord(alias) for alias in analysis.partial_candidate_aliases.get(label, [])) or "-"
                    lines.extend(
                        [
                            "",
                            f"{self.display_chord(label)} ({confidence:.0%})",
                            f"Observed tones: {notes}",
                            f"Alternate names: {aliases}",
                        ]
                    )
                    lines.extend(analysis.partial_candidate_explanations.get(label, ["No explanation available."]))
            if analysis.partial_hints:
                lines.extend(["", "Partial Harmony Hints", "-" * 21])
                lines.extend(analysis.partial_hints)
            return "\n".join(lines)

        def chord_selection_evidence_rows(
            self,
            notes: list[NoteEvent],
            start: float,
            end: float,
        ) -> tuple[list[str], dict[int, float]]:
            rows: list[str] = []
            totals: dict[int, float] = {}
            for note in sorted(notes, key=lambda item: (item.stem, item.start, item.pitch)):
                overlap = max(0.0, min(note.end, end) - max(note.start, start))
                if overlap <= 0:
                    continue
                velocity_energy = midi_velocity_energy(note.velocity)
                weight = overlap * velocity_energy
                totals[note.pitch % 12] = totals.get(note.pitch % 12, 0.0) + weight
                rows.append(
                    f"{note.stem:12} {self.display_note_name(note.pitch):4} pitch {note.pitch:3} "
                    f"start {format_time(note.start)} end {format_time(note.end)} "
                    f"overlap {overlap:.3f}s velocity {note.velocity:3} "
                    f"velocity energy {velocity_energy:.4f} note energy {weight:.4f}"
                )
            return rows, totals

        def chord_point_evidence_rows(
            self,
            notes: list[NoteEvent],
            seconds: float,
        ) -> tuple[list[str], dict[int, float]]:
            rows: list[str] = []
            totals: dict[int, float] = {}
            for note in sorted(active_notes_at(notes, seconds), key=lambda item: (item.stem, item.pitch, item.start)):
                weight = midi_velocity_energy(note.velocity)
                totals[note.pitch % 12] = totals.get(note.pitch % 12, 0.0) + weight
                rows.append(
                    f"{note.stem:12} {self.display_note_name(note.pitch):4} pitch {note.pitch:3} "
                    f"start {format_time(note.start)} end {format_time(note.end)} "
                    f"active at playhead velocity {note.velocity:3} velocity energy {weight:.4f}"
                )
            return rows, totals

        def pitch_class_list(self, pitch_classes: set[int]) -> str:
            if not pitch_classes:
                return "-"
            return ", ".join(self.display_pitch_class_name(pitch_class) for pitch_class in sorted(pitch_classes))

        def _set_chord_candidates(self, analysis) -> None:
            if analysis.candidates:
                self.chord_list.clear()
                for label, confidence in analysis.candidates:
                    display_label = self.display_chord(label)
                    note_names = self.display_chord_tones(label)
                    notes = self._candidate_notes_text(analysis, label)
                    aliases = analysis.candidate_aliases.get(label, [])
                    alias_text = ""
                    if aliases:
                        shown_aliases = ", ".join(self.display_chord(alias) for alias in aliases[:4])
                        if len(aliases) > 4:
                            shown_aliases += f", +{len(aliases) - 4} more"
                        alias_text = f"\naka: {shown_aliases}"
                    item = QListWidgetItem(f"{display_label}  {confidence:.0%}\n{notes}{alias_text}")
                    item.setData(Qt.UserRole, label)
                    item.setData(Qt.UserRole + 1, confidence)
                    item.setData(Qt.UserRole + 2, note_names)
                    item.setToolTip(
                        f"{display_label}\n"
                        f"Official chord tones: {notes}\n"
                        f"Alternate names: {', '.join(self.display_chord(alias) for alias in aliases) if aliases else '-'}\n"
                        f"Detector ranking score: {confidence:.0%}\n\n"
                        + "\n".join(analysis.candidate_explanations.get(label, []))
                    )
                    self.chord_list.addItem(item)
            else:
                self.chord_list.clear()
                self.chord_list.addItem("No full chord candidates here.")
                for label, confidence in analysis.partial_candidates:
                    display_label = self.display_chord(label)
                    note_names = self.display_chord_tones(label)
                    notes = self._partial_candidate_notes_text(analysis, label)
                    aliases = analysis.partial_candidate_aliases.get(label, [])
                    alias_text = ""
                    if aliases:
                        alias_text = f"\naka: {', '.join(self.display_chord(alias) for alias in aliases[:4])}"
                    item = QListWidgetItem(f"{display_label}  {confidence:.0%}\n{notes}{alias_text}")
                    item.setData(Qt.UserRole, label)
                    item.setData(Qt.UserRole + 1, confidence)
                    item.setData(Qt.UserRole + 2, note_names)
                    item.setToolTip(
                        f"{display_label}\n"
                        f"Observed shell tones: {notes}\n"
                        "Partial/shell candidate, not a full chord detection.\n\n"
                        + "\n".join(analysis.partial_candidate_explanations.get(label, []))
                    )
                    self.chord_list.addItem(item)
                for hint in analysis.partial_hints:
                    item = QListWidgetItem(hint)
                    item.setToolTip("Partial harmony hint. This is not a confirmed chord candidate.")
                    self.chord_list.addItem(item)
            self.select_first_chord_candidate()
            self.refresh_chord_actions()

        def select_first_chord_candidate(self) -> None:
            for row in range(self.chord_list.count()):
                item = self.chord_list.item(row)
                if item.data(Qt.UserRole):
                    self.chord_list.setCurrentItem(item)
                    return
            self.refresh_chord_keyboard()

        def handle_chord_selection_changed(self, *_args) -> None:
            self.refresh_chord_actions()
            self.refresh_chord_keyboard()

        def refresh_chord_keyboard(self) -> None:
            track_chord = self.active_chord_track_region()
            if track_chord is not None:
                note_names = self.display_chord_tones(track_chord.label)
                self.piano_chord_view.set_chord(
                    self.display_chord(track_chord.label),
                    note_names,
                    "Chord track",
                )
                return
            item = self.chord_list.currentItem()
            if item is None:
                self.piano_chord_view.set_chord(None, [])
                return
            label = item.data(Qt.UserRole)
            note_names = item.data(Qt.UserRole + 2) or []
            self.piano_chord_view.set_chord(label, note_names, "Inspector")

        def active_chord_track_region(self) -> ChordRegion | None:
            if self.timeline.selected_chord is not None:
                return self.timeline.selected_chord
            if self.editor_project is None:
                return None
            position = self.timeline.position
            for chord in reversed(self.editor_project.chords):
                if chord.start <= position < chord.end:
                    return chord
            return None

        def _candidate_notes_text(self, analysis, label: str) -> str:
            notes = self.display_chord_tones(label) if label else analysis.candidate_notes.get(label, [])
            if not notes:
                return "-"
            text = " - ".join(notes)
            if "/" in label:
                text += f"  bass {self.display_chord(label).split('/', 1)[1]}"
            return text

        def _partial_candidate_notes_text(self, analysis, label: str) -> str:
            notes = self.display_chord_tones(label) if label else analysis.partial_candidate_notes.get(label, [])
            if not notes:
                return "-"
            text = " - ".join(notes)
            if "/" in label:
                text += f"  bass {self.display_chord(label).split('/', 1)[1]}"
            return text

        def refresh_chord_actions(self) -> None:
            item = self.chord_list.currentItem()
            has_candidate = bool(item and item.data(Qt.UserRole))
            self.preview_chord_button.setEnabled(has_candidate)
            self.use_chord_button.setEnabled(has_candidate and self.timeline.selection_range() is not None)

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

    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("font-weight: 700; color: #374151; margin-top: 8px;")
        return label

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

    def _grid_control(layout: QGridLayout, row: int, column: int, label: str, default: str, widget: QWidget) -> None:
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
