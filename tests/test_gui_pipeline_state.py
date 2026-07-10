from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from pitchstems.gui_pipeline_state import (
    midi_stem_checkbox_state,
    pipeline_settings_widgets,
    restore_pipeline_settings,
    set_processing_state,
)


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


def test_midi_stem_checkbox_state_uses_default_for_new_pitched_stem() -> None:
    state = midi_stem_checkbox_state("bass", None, generate_midi=True, previous_checked=None)

    assert state.checked is True
    assert state.enabled is True
    assert state.tooltip == "Run Basic Pitch on this separated stem."


def test_midi_stem_checkbox_state_preserves_previous_choice_for_visible_stem() -> None:
    state = midi_stem_checkbox_state("bass", "bass", generate_midi=True, previous_checked=False)

    assert state.checked is False
    assert state.enabled is True


def test_midi_stem_checkbox_state_disables_when_midi_generation_is_off() -> None:
    state = midi_stem_checkbox_state("bass", None, generate_midi=False, previous_checked=True)

    assert state.checked is True
    assert state.enabled is False


def test_midi_stem_checkbox_state_excludes_unsaved_stem() -> None:
    state = midi_stem_checkbox_state("drums", "bass", generate_midi=True, previous_checked=True)

    assert state.checked is False
    assert state.enabled is False
    assert state.tooltip == "This stem is not being saved, so it cannot be analysed."


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


def test_set_processing_state_uses_worker_state_for_import_clear_button(monkeypatch) -> None:
    monkeypatch.setattr("pitchstems.gui_pipeline_state.refresh_midi_stem_checks", lambda *_args: None)
    window = _PipelineWindow()
    window.import_clip_picker._clip_range = object()

    set_processing_state(window, busy=False)

    assert window.import_clip_clear.enabled is True

    window.worker_jobs.active_token = 7

    set_processing_state(window, busy=False)

    assert window.import_clip_clear.enabled is False


def test_set_processing_state_disables_setup_repair_while_busy(monkeypatch) -> None:
    monkeypatch.setattr("pitchstems.gui_pipeline_state.refresh_midi_stem_checks", lambda *_args: None)
    window = _PipelineWindow()
    monkeypatch.setattr(window, "stop_import_clip_preview", lambda: None)

    set_processing_state(window, busy=True)

    assert window.repair_setup.enabled is False

    set_processing_state(window, busy=False)

    assert window.repair_setup.enabled is True

    window.setup_worker = _LiveWorker()
    set_processing_state(window, busy=False)

    assert window.repair_setup.enabled is False


def test_restore_pipeline_settings_rehydrates_saved_processing_choices(monkeypatch) -> None:
    window = _PipelineWindow()
    window.stem = _Combo([None, "bass"])
    window.bs_device = _Combo([None, "cpu", "cuda"])

    def rebuild_midi_checks(target) -> None:
        target.midi_stem_checks = {"bass": _Control(), "drums": _Control()}

    monkeypatch.setattr("pitchstems.gui_pipeline_state.refresh_midi_stem_checks", rebuild_midi_checks)

    restore_pipeline_settings(
        window,
        {
            "separation": {"selected_stem": "bass", "device": "cpu"},
            "generate_midi": True,
            "midi_policy": "all",
            "midi_stems": ["bass"],
            "midi": {
                "onset_threshold": 0.42,
                "minimum_frequency": 55.0,
                "sonify_midi": True,
                "sonification_samplerate": 48000,
            },
        },
    )

    assert window.stem.currentData() == "bass"
    assert window.bs_device.currentData() == "cpu"
    assert window.generate_midi.isChecked()
    assert window.onset_threshold.value() == 0.42
    assert window.minimum_frequency.value() == 55.0
    assert window.sonify_midi.isChecked()
    assert window.sonification_samplerate.value() == 48000
    assert window.midi_stem_checks["bass"].isChecked()
    assert not window.midi_stem_checks["drums"].isChecked()


class _Control:
    def __init__(self, checked: bool = False) -> None:
        self.enabled = False
        self._checked = checked
        self._value = 0

    def setEnabled(self, enabled: bool) -> None:
        self.enabled = enabled

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool) -> None:
        self._checked = checked

    def setValue(self, value) -> None:
        self._value = value

    def value(self):
        return self._value

    def blockSignals(self, _blocked: bool) -> bool:
        return False


class _Combo(_Control):
    def __init__(self, values: list[object]) -> None:
        super().__init__()
        self.values = values
        self.index = 0

    def findData(self, value: object) -> int:
        try:
            return self.values.index(value)
        except ValueError:
            return -1

    def setCurrentIndex(self, index: int) -> None:
        self.index = index

    def currentData(self):
        return self.values[self.index]


class _LiveWorker:
    def is_alive(self) -> bool:
        return True


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
        self.repair_setup = _Control()
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
