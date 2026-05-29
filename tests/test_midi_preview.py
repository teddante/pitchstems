from pathlib import Path
import json
import wave

from pitchstems.editor_project import NoteEvent
from pitchstems.midi_preview import render_midi_preview, render_note_preview, valid_preview_wav


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


def test_render_midi_preview_reuses_existing_preview(tmp_path: Path) -> None:
    notes = [NoteEvent(stem="piano", start=0.0, end=0.2, pitch=60, velocity=90)]
    preview = render_midi_preview("piano", notes, tmp_path, duration=0.4, sample_rate=8000)
    assert preview is not None
    original_mtime = preview.stat().st_mtime_ns

    output = render_midi_preview("piano", notes, tmp_path, duration=0.4, sample_rate=8000)

    assert output == preview
    assert preview.stat().st_mtime_ns == original_mtime
    with wave.open(str(output), "rb") as wav:
        assert wav.getframerate() == 8000


def test_render_midi_preview_replaces_stale_preview_metadata(tmp_path: Path) -> None:
    notes = [NoteEvent(stem="piano", start=0.0, end=0.2, pitch=60, velocity=90)]
    preview = render_midi_preview("piano", notes, tmp_path, duration=0.4, sample_rate=8000)
    assert preview is not None
    metadata = preview.with_suffix(".wav.json")
    metadata.write_text(json.dumps({"stale": True}), encoding="utf-8")

    output = render_midi_preview("piano", notes, tmp_path, duration=0.4, sample_rate=8000)

    assert output == preview
    assert json.loads(metadata.read_text(encoding="utf-8"))["format"] == "pitchstems-midi-preview"


def test_render_midi_preview_replaces_invalid_existing_preview(tmp_path: Path) -> None:
    preview = tmp_path / "piano_midi_preview.wav"
    preview.write_bytes(b"not a wav")
    notes = [NoteEvent(stem="piano", start=0.0, end=0.2, pitch=60, velocity=90)]

    output = render_midi_preview("piano", notes, tmp_path, duration=0.4, sample_rate=8000)

    assert output == preview
    with wave.open(str(preview), "rb") as wav:
        assert wav.getnframes() > 0


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


def test_valid_preview_wav_rejects_missing_or_invalid_files(tmp_path: Path) -> None:
    missing = tmp_path / "missing.wav"
    invalid = tmp_path / "invalid.wav"
    valid = tmp_path / "valid.wav"
    invalid.write_bytes(b"not a wav")
    _write_silent_wav(valid)

    assert not valid_preview_wav(missing)
    assert not valid_preview_wav(invalid)
    assert valid_preview_wav(valid)


def _write_silent_wav(path: Path, sample_rate: int = 8000) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * 16)
