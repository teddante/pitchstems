from __future__ import annotations

from dataclasses import dataclass

from pitchstems.acceleration import torch_status
from pitchstems.gui_helpers import blocked_signals, clear_layout
from pitchstems.gui_import_clip import can_clear_import_clip_selection, can_play_import_clip_preview
from pitchstems.gui_jobs import thread_is_alive
from pitchstems.gui_options import default_midi_checked, device_label, optional_frequency
from pitchstems.gui_pipeline_model import PipelinePageModel
from pitchstems.model_assets import model_asset_statuses
from pitchstems.model_catalog import DEFAULT_MODEL_KEY, model_choice
from pitchstems.separation import SeparationOptions
from pitchstems.transcription import MidiOptions


@dataclass(frozen=True)
class MidiStemCheckboxState:
    checked: bool
    enabled: bool
    tooltip: str


def set_processing_state(window, busy: bool) -> None:
    model = PipelinePageModel(
        busy=busy,
        has_result=window.current_result is not None,
        generate_midi=window.generate_midi.isChecked(),
    )
    window.drop_zone.setEnabled(model.drop_zone_enabled)
    if hasattr(window, "import_clip_picker"):
        if busy:
            window.stop_import_clip_preview()
        window.import_clip_picker.setEnabled(model.settings_enabled and window.import_clip_picker.duration_seconds > 0)
        window.import_clip_play.setEnabled(
            model.settings_enabled
            and can_play_import_clip_preview(
                window.import_clip_picker.path,
                window.import_clip_picker.selected_clip_range(),
                window.import_clip_picker.duration_seconds,
                window.worker_jobs.active_token,
            )
        )
        window.import_clip_stop.setEnabled(False)
        window.import_clip_clear.setEnabled(
            model.settings_enabled
            and can_clear_import_clip_selection(
                window.import_clip_picker.selected_clip_range(),
                window.worker_jobs.active_token,
            )
        )
    window.run_full.setEnabled(model.run_full_enabled)
    window.run_midi.setEnabled(model.run_midi_enabled)
    window.export_button.setEnabled(model.export_enabled)
    if getattr(window, "export_action", None) is not None:
        window.export_action.setEnabled(model.export_enabled)
    window.cancel_button.setEnabled(model.cancel_enabled)
    window.stem.setEnabled(model.settings_enabled)
    window.bs_device.setEnabled(model.settings_enabled)
    if hasattr(window, "repair_setup"):
        setup_worker = getattr(window, "setup_worker", None)
        window.repair_setup.setEnabled(not busy and not thread_is_alive(setup_worker))
    window.generate_midi.setEnabled(model.settings_enabled)
    for checkbox in window.midi_stem_checks.values():
        checkbox.setEnabled(model.midi_stem_checks_enabled)
    for widget in pipeline_settings_widgets(window):
        widget.setEnabled(model.settings_enabled)
    window.sonification_samplerate.setEnabled(
        model.settings_enabled and window.sonify_midi.isChecked()
    )
    if not busy:
        refresh_midi_stem_checks(window)


def pipeline_settings_widgets(window) -> tuple[object, ...]:
    return (
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
    )


def selected_separation_options(window) -> SeparationOptions:
    return SeparationOptions(
        model_key=DEFAULT_MODEL_KEY,
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


def restore_pipeline_settings(window, settings: dict) -> None:
    if not settings:
        return
    separation = settings.get("separation")
    if isinstance(separation, dict):
        selected_stem = separation.get("selected_stem")
        stem_index = window.stem.findData(selected_stem)
        if stem_index >= 0:
            with blocked_signals(window.stem):
                window.stem.setCurrentIndex(stem_index)
        device = separation.get("device")
        device_index = window.bs_device.findData(device)
        if device_index >= 0:
            with blocked_signals(window.bs_device):
                window.bs_device.setCurrentIndex(device_index)

    generate_midi = settings.get("generate_midi")
    midi_policy = settings.get("midi_policy")
    if isinstance(generate_midi, bool) or midi_policy == "none":
        with blocked_signals(window.generate_midi):
            window.generate_midi.setChecked(bool(generate_midi) and midi_policy != "none")

    midi = settings.get("midi")
    if isinstance(midi, dict):
        _restore_midi_widgets(window, midi)

    refresh_midi_stem_checks(window)
    midi_stems = settings.get("midi_stems")
    if isinstance(midi_stems, list) and midi_stems:
        selected = {stem.casefold() for stem in midi_stems if isinstance(stem, str)}
        for stem_name, checkbox in window.midi_stem_checks.items():
            with blocked_signals(checkbox):
                checkbox.setChecked(stem_name.casefold() in selected)


def _restore_midi_widgets(window, midi: dict) -> None:
    numeric_widgets = {
        "onset_threshold": window.onset_threshold,
        "frame_threshold": window.frame_threshold,
        "minimum_note_length": window.minimum_note_length,
        "minimum_frequency": window.minimum_frequency,
        "maximum_frequency": window.maximum_frequency,
        "midi_tempo": window.midi_tempo,
        "sonification_samplerate": window.sonification_samplerate,
    }
    for field, widget in numeric_widgets.items():
        value = midi.get(field)
        if value is None and field in {"minimum_frequency", "maximum_frequency"}:
            value = 0
        if isinstance(value, (int, float)):
            with blocked_signals(widget):
                widget.setValue(value)
    boolean_widgets = {
        "multiple_pitch_bends": window.multiple_pitch_bends,
        "melodia_trick": window.melodia_trick,
        "save_notes": window.save_notes,
        "save_model_outputs": window.save_model_outputs,
        "sonify_midi": window.sonify_midi,
    }
    for field, widget in boolean_widgets.items():
        value = midi.get(field)
        if isinstance(value, bool):
            with blocked_signals(widget):
                widget.setChecked(value)
    window.sonification_samplerate.setEnabled(window.sonify_midi.isChecked())


def refresh_midi_stem_checks(window, *_args) -> None:
    from PySide6.QtWidgets import QCheckBox

    choice = model_choice(DEFAULT_MODEL_KEY)
    saved_stem = window.stem.currentData()
    previous = {stem: checkbox.isChecked() for stem, checkbox in window.midi_stem_checks.items()}
    window.midi_stem_checks.clear()
    clear_layout(window.midi_stems_layout)

    for index, stem_name in enumerate(choice.stems):
        checkbox = QCheckBox(stem_name)
        state = midi_stem_checkbox_state(
            stem_name,
            saved_stem,
            generate_midi=window.generate_midi.isChecked(),
            previous_checked=previous.get(stem_name),
        )
        checkbox.setChecked(state.checked)
        checkbox.setEnabled(state.enabled)
        checkbox.setToolTip(state.tooltip)
        window.midi_stem_checks[stem_name] = checkbox
        window.midi_stems_layout.addWidget(checkbox, index // 2, index % 2)


def midi_stem_checkbox_state(
    stem_name: str,
    saved_stem: str | None,
    *,
    generate_midi: bool,
    previous_checked: bool | None,
) -> MidiStemCheckboxState:
    enabled = generate_midi and (saved_stem is None or stem_name == saved_stem)
    checked = previous_checked if previous_checked is not None else default_midi_checked(stem_name)
    if saved_stem is not None and stem_name != saved_stem:
        return MidiStemCheckboxState(
            checked=False,
            enabled=enabled,
            tooltip="This stem is not being saved, so it cannot be analysed.",
        )
    if stem_name.lower() == "drums":
        return MidiStemCheckboxState(
            checked=checked,
            enabled=enabled,
            tooltip="Off by default because Basic Pitch is not a drum transcription model.",
        )
    return MidiStemCheckboxState(
        checked=checked,
        enabled=enabled,
        tooltip="Run Basic Pitch on this separated stem.",
    )


def refresh_model_details(window, *_args) -> None:
    choice = model_choice(DEFAULT_MODEL_KEY)
    selected_stem = window.stem.currentData()

    with blocked_signals(window.stem):
        window.stem.clear()
        window.stem.addItem("All stems from this model", None)
        for stem_name in choice.stems:
            window.stem.addItem(stem_name, stem_name)
        selected_index = window.stem.findData(selected_stem)
        if selected_index >= 0:
            window.stem.setCurrentIndex(selected_index)
    refresh_midi_stem_checks(window)

    torch = torch_status()
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
        "MIDI: Spotify Basic Pitch ONNX; the active session provider is reported when transcription starts."
    )
    asset_statuses = model_asset_statuses(DEFAULT_MODEL_KEY)
    if asset_statuses and all(status.ok for status in asset_statuses):
        window.setup_status.setText("Model files: present (size checked).")
    else:
        missing = ", ".join(status.filename for status in asset_statuses if not status.ok)
        window.setup_status.setText(f"Model files: missing or incomplete: {missing}.")
    window.model_backend_detail.setText(
        f"BS-RoFormer: {choice.native_model_id}\n"
        f"Weights: {choice.filename}\n"
        f"Config: {choice.config_filename}\n"
        f"Calls: bs_roformer.inference.proc_folder -> basic_pitch.inference.predict_and_save"
    )
