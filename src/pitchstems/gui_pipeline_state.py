from __future__ import annotations

from pitchstems.acceleration import onnxruntime_status, torch_status
from pitchstems.gui_options import default_midi_checked, device_label, optional_frequency
from pitchstems.model_catalog import model_choice
from pitchstems.separation import SeparationOptions
from pitchstems.transcription import MidiOptions


def set_processing_state(window, busy: bool) -> None:
    window.drop_zone.setEnabled(not busy)
    window.run_full.setEnabled(not busy)
    window.run_midi.setEnabled((not busy) and window.current_result is not None)
    window.stem.setEnabled(not busy)
    window.bs_device.setEnabled(not busy)
    window.generate_midi.setEnabled(not busy)
    for checkbox in window.midi_stem_checks.values():
        checkbox.setEnabled(not busy and window.generate_midi.isChecked())
    for widget in [
        window.onset_threshold,
        window.frame_threshold,
        window.minimum_note_length,
        window.minimum_frequency,
        window.maximum_frequency,
        window.midi_tempo,
        window.melodia_trick,
        window.multiple_pitch_bends,
        window.save_notes,
        window.save_model_outputs,
        window.sonify_midi,
        window.sonification_samplerate,
        window.create_zip,
        window.open_when_done,
    ]:
        widget.setEnabled(not busy)
    if not busy:
        window.refresh_midi_stem_checks()


def selected_model_key(_window) -> str:
    return "bs_roformer_sw"


def selected_separation_options(window) -> SeparationOptions:
    return SeparationOptions(
        model_key=window.selected_model_key(),
        selected_stem=window.stem.currentData(),
        device=window.bs_device.currentData(),
    )


def selected_midi_options(window) -> MidiOptions:
    return MidiOptions(
        onset_threshold=window.onset_threshold.value(),
        frame_threshold=window.frame_threshold.value(),
        minimum_note_length=window.minimum_note_length.value(),
        minimum_frequency=optional_frequency(window.minimum_frequency.value()),
        maximum_frequency=optional_frequency(window.maximum_frequency.value()),
        multiple_pitch_bends=window.multiple_pitch_bends.isChecked(),
        melodia_trick=window.melodia_trick.isChecked(),
        midi_tempo=window.midi_tempo.value(),
        save_notes=window.save_notes.isChecked(),
        save_model_outputs=window.save_model_outputs.isChecked(),
        sonify_midi=window.sonify_midi.isChecked(),
        sonification_samplerate=window.sonification_samplerate.value(),
    )


def selected_midi_stems(window) -> set[str]:
    if not window.generate_midi.isChecked():
        return set()
    return {
        stem_name
        for stem_name, checkbox in window.midi_stem_checks.items()
        if checkbox.isChecked()
    }


def refresh_midi_stem_checks(window, *_args) -> None:
    from PySide6.QtWidgets import QCheckBox

    choice = model_choice(window.selected_model_key())
    saved_stem = window.stem.currentData()
    previous = {stem: checkbox.isChecked() for stem, checkbox in window.midi_stem_checks.items()}
    window.midi_stem_checks.clear()
    _clear_layout(window.midi_stems_layout)

    for index, stem_name in enumerate(choice.stems):
        checkbox = QCheckBox(stem_name)
        checkbox.setChecked(previous.get(stem_name, default_midi_checked(stem_name)))
        can_run = window.generate_midi.isChecked() and (saved_stem is None or stem_name == saved_stem)
        checkbox.setEnabled(can_run)
        if saved_stem is not None and stem_name != saved_stem:
            checkbox.setChecked(False)
            checkbox.setToolTip("This stem is not being saved, so it cannot be analysed.")
        elif stem_name.lower() == "drums":
            checkbox.setToolTip("Off by default because Basic Pitch is not a drum transcription model.")
        else:
            checkbox.setToolTip("Run Basic Pitch on this separated stem.")
        window.midi_stem_checks[stem_name] = checkbox
        window.midi_stems_layout.addWidget(checkbox, index // 2, index % 2)


def refresh_model_details(window, *_args) -> None:
    choice = model_choice(window.selected_model_key())

    window.stem.blockSignals(True)
    window.stem.clear()
    window.stem.addItem("All stems from this model", None)
    for stem_name in choice.stems:
        window.stem.addItem(stem_name, stem_name)
    window.stem.blockSignals(False)
    window.refresh_midi_stem_checks()

    torch = torch_status()
    ort = onnxruntime_status()
    window.model_title.setText(choice.label)
    window.model_summary.setText(choice.summary)
    window.model_facts.setText(
        f"Best for: {choice.best_for}\n"
        f"Creates: {', '.join(choice.stems)}\n"
        f"Evidence: {choice.score_summary}"
    )
    window.model_runtime.setText(
        f"Separation: {choice.source} on {device_label(window.bs_device.currentData(), torch.cuda_available)}. "
        f"MIDI: Spotify Basic Pitch ONNX on {'ONNX CUDA' if ort.has_cuda else 'ONNX CPU'}."
    )
    window.model_backend_detail.setText(
        f"BS-RoFormer: {choice.native_model_id}\n"
        f"Weights: {choice.filename or 'provided by registry'}\n"
        f"Config: {choice.config_filename or 'provided by registry'}\n"
        f"Calls: bs_roformer.inference.proc_folder -> basic_pitch.inference.predict_and_save"
    )


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()
