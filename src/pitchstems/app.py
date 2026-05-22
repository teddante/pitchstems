from __future__ import annotations

import os
import queue
import threading
from pathlib import Path

from pitchstems.acceleration import onnxruntime_status, torch_status
from pitchstems.model_catalog import model_choice
from pitchstems.pipeline import PipelineResult, process_audio_file, process_midi_from_stems
from pitchstems.separation import SeparationOptions, StemResult
from pitchstems.transcription import MidiOptions


def main() -> int:
    try:
        from PySide6.QtCore import QTimer, Qt
        from PySide6.QtWidgets import (
            QApplication,
            QCheckBox,
            QComboBox,
            QDoubleSpinBox,
            QFileDialog,
            QGridLayout,
            QGroupBox,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QMainWindow,
            QPushButton,
            QSpinBox,
            QTabWidget,
            QTextEdit,
            QVBoxLayout,
            QWidget,
        )
    except ImportError:
        print("PySide6 is not installed. Install with `pip install -e .[gui]`.")
        return 1

    class DropZone(QLabel):
        def __init__(self) -> None:
            super().__init__("Drop an audio file here")
            self.setAcceptDrops(True)
            self.setFocusPolicy(Qt.StrongFocus)
            self.setAlignment(Qt.AlignCenter)
            self.setMinimumHeight(105)
            self.setMaximumHeight(130)
            self.setStyleSheet(
                """
                QLabel {
                    border: 2px dashed #4c7aaf;
                    border-radius: 8px;
                    color: #1f2937;
                    font-size: 19px;
                    background: #f8fafc;
                }
                """
            )
            self.path: Path | None = None
            self.on_path_changed = None

        def dragEnterEvent(self, event) -> None:
            if event.mimeData().hasUrls():
                event.acceptProposedAction()

        def dropEvent(self, event) -> None:
            urls = event.mimeData().urls()
            if urls:
                self.path = Path(urls[0].toLocalFile())
                self.setText(str(self.path))
                if self.on_path_changed:
                    self.on_path_changed(self.path)

    class NoWheelComboBox(QComboBox):
        def wheelEvent(self, event) -> None:
            event.ignore()

    class NoWheelDoubleSpinBox(QDoubleSpinBox):
        def wheelEvent(self, event) -> None:
            event.ignore()

    class NoWheelSpinBox(QSpinBox):
        def wheelEvent(self, event) -> None:
            event.ignore()

    class MainWindow(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("PitchStems")
            self.resize(1220, 780)
            self.choice = model_choice("bs_roformer_sw")
            self.messages: queue.Queue[str] = queue.Queue()
            self.worker: threading.Thread | None = None
            self.latest_output_dir: Path | None = None
            self.current_result: PipelineResult | None = None
            self.current_stems: list[StemResult] = []
            self.current_input_stem: str | None = None

            self.drop_zone = DropZone()
            self.drop_zone.on_path_changed = self.reset_stage_state
            self.output_dir = QLineEdit(str(Path.cwd() / "pitchstems-output"))
            self.output_dir.setReadOnly(True)
            self.choose_output = QPushButton("Choose Output")
            self.open_output = QPushButton("Open Output Folder")
            self.open_output.setEnabled(False)

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

            self.create_zip = QCheckBox("Create ZIP export")
            self.create_zip.setChecked(True)
            self.open_when_done = QCheckBox("Open output folder when finished")
            self.open_when_done.setChecked(True)

            self.run_full = QPushButton("Run separation + MIDI")
            self.run_midi = QPushButton("Rerun MIDI only")
            self.run_midi.setEnabled(False)
            self.log = QTextEdit()
            self.log.setReadOnly(True)

            output_row = QHBoxLayout()
            output_row.setSpacing(10)
            output_row.addWidget(self.output_dir, 1)
            output_row.addWidget(self.choose_output)
            output_row.addWidget(self.open_output)

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

            layout = QVBoxLayout()
            layout.setContentsMargins(12, 12, 12, 12)
            layout.setSpacing(10)
            layout.addWidget(self.drop_zone)
            layout.addLayout(output_row)
            layout.addLayout(main_row, 1)
            layout.addLayout(action_row)
            layout.addWidget(self.log, 1)

            root = QWidget()
            root.setLayout(layout)
            self.setCentralWidget(root)

            self.choose_output.clicked.connect(self.pick_output_dir)
            self.open_output.clicked.connect(self.open_latest_output)
            self.run_full.clicked.connect(self.start_full_processing)
            self.run_midi.clicked.connect(self.start_midi_processing)
            self.bs_device.currentIndexChanged.connect(self.refresh_model_details)
            self.generate_midi.toggled.connect(self.refresh_midi_stem_checks)
            self.sonify_midi.toggled.connect(self.sonification_samplerate.setEnabled)

            self.refresh_model_details()
            self.drop_zone.setFocus()

            self.timer = QTimer(self)
            self.timer.timeout.connect(self.flush_messages)
            self.timer.start(100)

        def pick_output_dir(self) -> None:
            directory = QFileDialog.getExistingDirectory(self, "Choose output directory")
            if directory:
                self.output_dir.setText(directory)

        def start_full_processing(self) -> None:
            if self.worker and self.worker.is_alive():
                return
            if not self.drop_zone.path:
                self.append_log("Drop an audio file first.")
                return

            self.set_processing_state(True)
            self.open_output.setEnabled(False)
            self.append_log("Starting separation + MIDI pipeline...")
            self.worker = threading.Thread(target=self.run_full_pipeline, daemon=True)
            self.worker.start()

        def start_midi_processing(self) -> None:
            if self.worker and self.worker.is_alive():
                return
            if not self.current_result or not self.current_stems or not self.current_input_stem:
                self.append_log("Run separation first. Then MIDI can be rerun from those stems.")
                return

            self.set_processing_state(True)
            self.append_log("Rerunning MIDI from existing stems...")
            self.worker = threading.Thread(target=self.run_midi_stage, daemon=True)
            self.worker.start()

        def run_full_pipeline(self) -> None:
            try:
                midi_stems = self.selected_midi_stems()
                result = process_audio_file(
                    self.drop_zone.path,
                    Path(self.output_dir.text()),
                    separation_options=self.selected_separation_options(),
                    generate_midi=self.generate_midi.isChecked() and bool(midi_stems),
                    midi_policy="all",
                    midi_options=self.selected_midi_options(),
                    midi_stems=midi_stems,
                    create_zip=self.create_zip.isChecked(),
                    log=self.messages.put,
                )
                self.messages.put(("RESULT", result))
                self.messages.put(f"Export ready: {result.zip_path or result.project_dir / 'export'}")
            except Exception as exc:
                self.messages.put(f"Error: {exc}")
            finally:
                self.messages.put("__ENABLE_PROCESS__")

        def run_midi_stage(self) -> None:
            try:
                midi_stems = self.selected_midi_stems()
                result = process_midi_from_stems(
                    project_dir=self.current_result.project_dir,
                    input_stem=self.current_input_stem,
                    normalized_audio=self.current_result.normalized_audio,
                    stems=self.current_stems,
                    midi_policy="all",
                    midi_options=self.selected_midi_options(),
                    midi_stems=midi_stems,
                    create_zip=self.create_zip.isChecked(),
                    log=self.messages.put,
                )
                self.messages.put(("RESULT", result))
                self.messages.put(f"Updated MIDI export: {result.zip_path or result.project_dir / 'export'}")
            except Exception as exc:
                self.messages.put(f"Error: {exc}")
            finally:
                self.messages.put("__ENABLE_PROCESS__")

        def flush_messages(self) -> None:
            while True:
                try:
                    message = self.messages.get_nowait()
                except queue.Empty:
                    return
                if isinstance(message, tuple) and message[0] == "RESULT":
                    self.set_current_result(message[1])
                elif message == "__ENABLE_PROCESS__":
                    self.set_processing_state(False)
                elif message.startswith("__OUTPUT_DIR__"):
                    self.latest_output_dir = Path(message.removeprefix("__OUTPUT_DIR__"))
                    self.open_output.setEnabled(True)
                    if self.open_when_done.isChecked():
                        self.open_latest_output()
                else:
                    self.append_log(message)

        def append_log(self, message: str) -> None:
            self.log.append(message)

        def set_current_result(self, result: PipelineResult) -> None:
            self.current_result = result
            self.current_stems = result.stems
            self.current_input_stem = result.normalized_audio.stem
            self.latest_output_dir = result.project_dir / "export"
            self.open_output.setEnabled(True)
            self.run_midi.setEnabled(True)
            self.separation_status.setText(f"Ready: {len(result.stems)} stems saved in {result.project_dir / 'stems'}")
            self.midi_status.setText(
                f"Ready: {len(result.midi_files)} MIDI files. Change Basic Pitch settings or MIDI stem ticks, then use Rerun MIDI only."
            )
            if self.open_when_done.isChecked():
                self.open_latest_output()

        def reset_stage_state(self, _path: Path | None = None) -> None:
            self.current_result = None
            self.current_stems = []
            self.current_input_stem = None
            self.run_midi.setEnabled(False)
            self.separation_status.setText("Not run yet.")
            self.midi_status.setText("Run the full pipeline first, then MIDI can be rerun without separating again.")

        def set_processing_state(self, busy: bool) -> None:
            self.drop_zone.setEnabled(not busy)
            self.choose_output.setEnabled(not busy)
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
                minimum_frequency=_optional_frequency(self.minimum_frequency.value()),
                maximum_frequency=_optional_frequency(self.maximum_frequency.value()),
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
                if checkbox.isEnabled() and checkbox.isChecked()
            }

        def refresh_midi_stem_checks(self, *_args) -> None:
            choice = model_choice(self.selected_model_key())
            saved_stem = self.stem.currentData()
            previous = {stem: checkbox.isChecked() for stem, checkbox in self.midi_stem_checks.items()}
            self.midi_stem_checks.clear()
            _clear_layout(self.midi_stems_layout)

            for index, stem_name in enumerate(choice.stems):
                checkbox = QCheckBox(stem_name)
                checkbox.setChecked(previous.get(stem_name, _default_midi_checked(stem_name)))
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
                f"Separation: {choice.source} on {_device_label(self.bs_device.currentData(), torch.cuda_available)}. "
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
            target.mkdir(parents=True, exist_ok=True)
            os.startfile(target)

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

    def _optional_frequency(value: float) -> float | None:
        return value if value > 0 else None

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

    def _default_midi_checked(stem_name: str) -> bool:
        return stem_name.lower() not in {"drums", "drum", "wet"}

    def _device_label(device: str | None, cuda_available: bool) -> str:
        if device == "cpu":
            return "PyTorch CPU (forced)"
        if device:
            return f"PyTorch CUDA ({device})"
        return "PyTorch CUDA (auto)" if cuda_available else "PyTorch CPU (auto fallback)"

    app = QApplication([])
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
