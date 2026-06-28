from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from pitchstems.gui_pipeline_state import pipeline_settings_widgets, set_processing_state


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


def test_set_processing_state_uses_preview_range_for_import_play_button(monkeypatch) -> None:
    monkeypatch.setattr("pitchstems.gui_pipeline_state.refresh_midi_stem_checks", lambda *_args: None)
    window = _PipelineWindow()
    window.import_clip_picker.path = Path("song.wav")
    window.import_clip_picker.duration_seconds = 0.01

    set_processing_state(window, busy=False)

    assert window.import_clip_play.enabled is False

    window.import_clip_picker.duration_seconds = 5.0

    set_processing_state(window, busy=False)

    assert window.import_clip_play.enabled is True


class _Control:
    def __init__(self, checked: bool = False) -> None:
        self.enabled = False
        self._checked = checked

    def setEnabled(self, enabled: bool) -> None:
        self.enabled = enabled

    def isChecked(self) -> bool:
        return self._checked


class _ImportClipPicker(_Control):
    def __init__(self) -> None:
        super().__init__()
        self.path: Path | None = None
        self.duration_seconds = 0.0
        self._clip_range = None

    def selected_clip_range(self):
        return self._clip_range


class _PipelineWindow:
    def __init__(self) -> None:
        self.current_result = None
        self.worker_jobs = SimpleNamespace(active_token=None)
        self.drop_zone = _Control()
        self.import_clip_picker = _ImportClipPicker()
        self.import_clip_play = _Control()
        self.import_clip_stop = _Control()
        self.import_clip_clear = _Control()
        self.run_full = _Control()
        self.run_midi = _Control()
        self.export_button = _Control()
        self.export_action = None
        self.cancel_button = _Control()
        self.stem = _Control()
        self.bs_device = _Control()
        self.generate_midi = _Control(False)
        self.midi_stem_checks = {}
        self.onset_threshold = _Control()
        self.frame_threshold = _Control()
        self.minimum_note_length = _Control()
        self.minimum_frequency = _Control()
        self.maximum_frequency = _Control()
        self.midi_tempo = _Control()
        self.melodia_trick = _Control()
        self.multiple_pitch_bends = _Control()
        self.save_notes = _Control()
        self.save_model_outputs = _Control()
        self.sonify_midi = _Control()
        self.sonification_samplerate = _Control()
        self.open_when_done = _Control()

    def stop_import_clip_preview(self) -> None:
        raise AssertionError("idle state should not stop preview playback")
