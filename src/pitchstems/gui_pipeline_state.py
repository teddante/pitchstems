from __future__ import annotations

from pitchstems.acceleration import onnxruntime_status, torch_status
from pitchstems.gui_helpers import clear_layout
from pitchstems.gui_options import default_midi_checked, device_label, optional_frequency
from pitchstems.gui_pipeline_model import PipelinePageModel
from pitchstems.model_catalog import DEFAULT_MODEL_KEY, model_choice
from pitchstems.separation import SeparationOptions
from pitchstems.transcription import MidiOptions


def set_processing_state(window, busy: bool) -> None:
    model = PipelinePageModel(
        busy=busy,
        has_result=window.current_result is not None,
        generate_midi=window.generate_midi.isChecked(),
    )
    window.drop_zone.setEnabled(model.drop_zone_enabled)
    window.run_full.setEnabled(model.run_full_enabled)
    window.run_midi.setEnabled(model.run_midi_enabled)
    window.export_button.setEnabled(model.export_enabled)
    if getattr(window, "export_action", None) is not None:
        window.export_action.setEnabled(model.export_enabled)
    window.cancel_button.setEnabled(model.cancel_enabled)
    window.stem.setEnabled(model.settings_enabled)
    window.bs_device.setEnabled(model.settings_enabled)
    window.generate_midi.setEnabled(model.settings_enabled)
    for checkbox in window.midi_stem_checks.values():
        checkbox.setEnabled(model.midi_stem_checks_enabled)
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
        window.open_when_done,
    ]:
        widget.setEnabled(model.settings_enabled)
    if not busy:
        window.refresh_midi_stem_checks()


def selected_model_key(window) -> str:
    return DEFAULT_MODEL_KEY


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
    clear_layout(window.midi_stems_layout)

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
    window.separation_card.setTitle(choice.label)
    window.model_summary.setText(choice.summary)
    window.model_facts.setText(
        f"Best for: {choice.best_for}\n"
        f"Creates: {', '.join(choice.stems)}\n"
        f"Quality: {choice.quality_note}\n"
        f"Speed: {choice.speed_note}\n"
        f"Acceleration: {choice.gpu_note}\n"
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
