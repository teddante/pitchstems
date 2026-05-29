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


def test_render_midi_preview_sanitizes_stem_preview_filename(tmp_path: Path) -> None:
    notes = [NoteEvent(stem="../bad/stem", start=0.0, end=0.2, pitch=60, velocity=90)]

    output = render_midi_preview("../bad/stem", notes, tmp_path, duration=0.4, sample_rate=8000)

    assert output == tmp_path / "bad_stem_midi_preview.wav"
    assert output.exists()
    assert output.parent == tmp_path


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


def test_render_midi_preview_metadata_uses_compact_note_digest(tmp_path: Path) -> None:
    notes = [
        NoteEvent(stem="piano", start=index * 0.01, end=index * 0.01 + 0.02, pitch=60 + index % 12, velocity=72)
        for index in range(120)
    ]

    preview = render_midi_preview("piano", notes, tmp_path, duration=1.5, sample_rate=8000)

    assert preview is not None
    metadata = json.loads(preview.with_suffix(".wav.json").read_text(encoding="utf-8"))
    assert "notes" not in metadata
    assert metadata["note_count"] == len(notes)
    assert len(metadata["note_digest"]) == 64


def test_render_midi_preview_metadata_digest_changes_with_note_content(tmp_path: Path) -> None:
    notes = [NoteEvent(stem="piano", start=0.0, end=0.2, pitch=60, velocity=90)]
    changed_notes = [NoteEvent(stem="piano", start=0.0, end=0.2, pitch=61, velocity=90)]
    preview = render_midi_preview("piano", notes, tmp_path, duration=0.4, sample_rate=8000)
    assert preview is not None
    metadata_path = preview.with_suffix(".wav.json")
    original_digest = json.loads(metadata_path.read_text(encoding="utf-8"))["note_digest"]

    render_midi_preview("piano", changed_notes, tmp_path, duration=0.4, sample_rate=8000)

    assert json.loads(metadata_path.read_text(encoding="utf-8"))["note_digest"] != original_digest


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


def test_render_note_preview_uses_safe_fallback_names(tmp_path: Path) -> None:
    notes = [NoteEvent(stem="official-chord", start=0.0, end=0.5, pitch=60, velocity=90)]

    empty_output = render_note_preview("...", notes, tmp_path, duration=0.5, sample_rate=8000)
    reserved_output = render_note_preview("CON", notes, tmp_path, duration=0.5, sample_rate=8000)

    assert empty_output == tmp_path / "preview.wav"
    assert reserved_output == tmp_path / "preview_CON.wav"
    assert empty_output.exists()
    assert reserved_output.exists()


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
