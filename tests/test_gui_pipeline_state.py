from __future__ import annotations

from types import SimpleNamespace

from pitchstems.gui_pipeline_state import pipeline_settings_widgets


def test_pipeline_settings_widgets_lists_controls_in_stable_order() -> None:
    names = (
        "onset_threshold",
        "frame_threshold",
        "minimum_note_length",
        "minimum_frequency",
        "maximum_frequency",
        "midi_tempo",
        "melodia_trick",
        "multiple_pitch_bends",
        "save_notes",
        "save_model_outputs",
        "sonify_midi",
        "sonification_samplerate",
        "open_when_done",
    )
    controls = {name: object() for name in names}
    window = SimpleNamespace(**controls)

    assert pipeline_settings_widgets(window) == tuple(controls[name] for name in names)
