from pitchstems.editor_project import NoteEvent
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
