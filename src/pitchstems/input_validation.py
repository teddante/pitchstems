from __future__ import annotations

from pathlib import Path


SUPPORTED_AUDIO_SUFFIXES = {
    ".aac",
    ".aif",
    ".aiff",
    ".flac",
    ".m4a",
    ".mp3",
    ".ogg",
    ".opus",
    ".wav",
    ".wma",
}


def validate_audio_input(path: Path) -> str | None:
    if not path.exists():
        return f"Audio file does not exist: {path}"
    if not path.is_file():
        return "Choose an audio file, not a folder."
    if path.suffix.lower() not in SUPPORTED_AUDIO_SUFFIXES:
        return f"Unsupported audio file type: {path.suffix or '(none)'}"
    return None
