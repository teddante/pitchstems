from __future__ import annotations

from pathlib import Path

from pitchstems.input_validation import validate_audio_input


def test_validate_audio_input_rejects_directory(tmp_path: Path) -> None:
    error = validate_audio_input(tmp_path)
    assert error == "Choose an audio file, not a folder."


def test_validate_audio_input_rejects_unsupported_suffix(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("not audio", encoding="utf-8")
    assert "Unsupported audio file type" in validate_audio_input(path)


def test_validate_audio_input_accepts_common_audio_suffix(tmp_path: Path) -> None:
    path = tmp_path / "song.wav"
    path.write_bytes(b"RIFF")
    assert validate_audio_input(path) is None
