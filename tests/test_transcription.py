from __future__ import annotations

import math
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

from pitchstems import transcription


def test_midi_options_reject_invalid_numeric_ranges() -> None:
    for kwargs in (
        {"onset_threshold": math.nan},
        {"frame_threshold": 1.1},
        {"minimum_note_length": -1.0},
        {"minimum_frequency": 880.0, "maximum_frequency": 440.0},
        {"midi_tempo": math.inf},
        {"sonification_samplerate": 0},
    ):
        try:
            transcription.MidiOptions(**kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected invalid MIDI options to fail: {kwargs}")


def test_transcription_reuses_model_and_reports_active_provider(monkeypatch, tmp_path: Path) -> None:
    loads: list[str] = []
    model_arguments: list[object] = []

    class FakeSession:
        def get_providers(self) -> list[str]:
            return ["CPUExecutionProvider"]

    class FakeModel:
        def __init__(self, model_path: str) -> None:
            loads.append(model_path)
            self.model = FakeSession()

    def fake_predict_and_save(audio_paths, output_directory, *, model_or_model_path, **_kwargs):
        model_arguments.append(model_or_model_path)
        audio_path = Path(audio_paths[0])
        (Path(output_directory) / f"{audio_path.stem}.mid").write_bytes(b"MThd")

    basic_pitch = ModuleType("basic_pitch")
    basic_pitch.FilenameSuffix = SimpleNamespace(onnx="onnx")  # type: ignore[attr-defined]
    basic_pitch.build_icassp_2022_model_path = lambda _suffix: Path("model.onnx")  # type: ignore[attr-defined]
    inference = ModuleType("basic_pitch.inference")
    inference.Model = FakeModel  # type: ignore[attr-defined]
    inference.predict_and_save = fake_predict_and_save  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "basic_pitch", basic_pitch)
    monkeypatch.setitem(sys.modules, "basic_pitch.inference", inference)
    transcription._load_basic_pitch_model.cache_clear()
    messages: list[str] = []

    for stem in ("bass", "vocals"):
        audio_path = tmp_path / f"{stem}.wav"
        audio_path.write_bytes(b"wav")
        transcription.transcribe_stem_to_midi(
            stem,
            audio_path,
            tmp_path / stem,
            log=messages.append,
        )

    assert loads == ["model.onnx"]
    assert len(model_arguments) == 2
    assert model_arguments[0] is model_arguments[1]
    assert any("Basic Pitch (ONNX CPU)" in message for message in messages)
    transcription._load_basic_pitch_model.cache_clear()
