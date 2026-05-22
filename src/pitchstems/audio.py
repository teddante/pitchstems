from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class FFmpegNotFoundError(RuntimeError):
    """Raised when FFmpeg is not available on PATH."""


def require_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FFmpegNotFoundError(
            "FFmpeg was not found on PATH. Install FFmpeg before processing audio."
        )
    return ffmpeg


def normalize_to_wav(input_path: Path, output_path: Path, sample_rate: int = 44_100) -> Path:
    """Convert any FFmpeg-readable audio file into a stereo PCM WAV."""
    ffmpeg = require_ffmpeg()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        "2",
        "-ar",
        str(sample_rate),
        "-c:a",
        "pcm_s16le",
        str(output_path),
    ]
    subprocess.run(command, check=True)
    return output_path

