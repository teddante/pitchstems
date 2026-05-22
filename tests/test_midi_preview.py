from pathlib import Path
import wave

from pitchstems.editor_project import NoteEvent
from pitchstems.midi_preview import render_midi_preview


def test_render_midi_preview_writes_wav(tmp_path: Path) -> None:
    notes = [
        NoteEvent(stem="piano", start=0.0, end=0.2, pitch=60, velocity=90),
        NoteEvent(stem="piano", start=0.2, end=0.4, pitch=64, velocity=90),
    ]

    output = render_midi_preview("piano", notes, tmp_path, duration=0.4, sample_rate=8000)

    assert output == tmp_path / "piano_midi_preview.wav"
    with wave.open(str(output), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getframerate() == 8000
        assert wav.getnframes() > 0


def test_render_midi_preview_skips_stems_without_notes(tmp_path: Path) -> None:
    notes = [NoteEvent(stem="bass", start=0.0, end=0.2, pitch=40, velocity=90)]

    assert render_midi_preview("piano", notes, tmp_path, duration=0.4, sample_rate=8000) is None
