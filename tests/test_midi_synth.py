from array import array

import pytest

import pitchstems.midi_synth as midi_synth
from pitchstems.editor_models import NoteEvent
from pitchstems.midi_synth import MidiSynthEngine


def test_midi_synth_renders_enabled_track_audio() -> None:
    engine = MidiSynthEngine(
        [NoteEvent(stem="piano", start=0.0, end=0.2, pitch=60, velocity=90)],
        duration=0.2,
        sample_rate=8000,
    )

    audio = engine.render(0.0, 800, {"piano": 0.8})

    assert len(audio) == 1600
    assert any(audio)


def test_midi_synth_renders_silence_for_muted_tracks() -> None:
    engine = MidiSynthEngine(
        [NoteEvent(stem="piano", start=0.0, end=0.2, pitch=60, velocity=90)],
        duration=0.2,
        sample_rate=8000,
    )

    audio = engine.render(0.0, 800, {"piano": 0.0})

    assert audio == b"\x00" * 1600


def test_midi_synth_renders_from_seek_position_inside_note() -> None:
    engine = MidiSynthEngine(
        [NoteEvent(stem="bass", start=1.0, end=2.0, pitch=40, velocity=100)],
        duration=2.0,
        sample_rate=8000,
    )

    before_note = engine.render(0.0, 400, {"bass": 1.0})
    inside_note = engine.render(1.25, 400, {"bass": 1.0})

    assert before_note == b"\x00" * 800
    assert any(inside_note)


def test_midi_synth_numpy_and_python_paths_agree(monkeypatch) -> None:
    if midi_synth._np is None:
        pytest.skip("NumPy is not installed")
    notes = [
        NoteEvent(stem="piano", start=0.0, end=0.3, pitch=60, velocity=90),
        NoteEvent(stem="piano", start=0.1, end=0.5, pitch=64, velocity=70),
        NoteEvent(stem="bass", start=0.05, end=0.4, pitch=40, velocity=110),
    ]
    engine = MidiSynthEngine(notes, duration=0.5, sample_rate=8000)
    volumes = {"piano": 0.8, "bass": 1.0}

    fast = array("h", engine.render(0.02, 2000, volumes))
    fast_samples = engine.render_samples(0.02, 2000, volumes)
    monkeypatch.setattr(midi_synth, "_np", None)
    slow = array("h", engine.render(0.02, 2000, volumes))
    slow_samples = engine.render_samples(0.02, 2000, volumes)

    assert any(fast)
    assert max(abs(a - b) for a, b in zip(fast, slow, strict=True)) <= 1
    assert max(abs(a - b) for a, b in zip(fast_samples, slow_samples, strict=True)) < 1e-5
