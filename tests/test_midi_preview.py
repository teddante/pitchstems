from pathlib import Path
import wave

from pitchstems.editor_models import NoteEvent
from pitchstems.midi_preview import render_note_preview


def test_render_note_preview_writes_named_wav(tmp_path: Path) -> None:
    notes = [
        NoteEvent(stem="official-chord", start=0.0, end=0.5, pitch=60, velocity=90),
        NoteEvent(stem="official-chord", start=0.0, end=0.5, pitch=64, velocity=90),
        NoteEvent(stem="official-chord", start=0.0, end=0.5, pitch=67, velocity=90),
    ]

    output = render_note_preview("C major", notes, tmp_path, duration=0.5, sample_rate=8000)

    assert output == tmp_path / "C_major.wav"
    with wave.open(str(output), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getframerate() == 8000
        assert wav.getnframes() > 0


def test_render_note_preview_uses_safe_fallback_names(tmp_path: Path) -> None:
    notes = [NoteEvent(stem="official-chord", start=0.0, end=0.5, pitch=60, velocity=90)]

    empty_output = render_note_preview("...", notes, tmp_path, duration=0.5, sample_rate=8000)
    reserved_output = render_note_preview("CON", notes, tmp_path, duration=0.5, sample_rate=8000)

    assert empty_output == tmp_path / "preview.wav"
    assert reserved_output == tmp_path / "preview_CON.wav"
    assert empty_output.exists()
    assert reserved_output.exists()
