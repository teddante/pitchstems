from __future__ import annotations

import json
import shutil
import subprocess
import sys
from array import array
from dataclasses import dataclass
from pathlib import Path

from pitchstems.audio_clip import AudioClipRange


class FFmpegNotFoundError(RuntimeError):
    """Raised when FFmpeg is not available on PATH."""


def require_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FFmpegNotFoundError(
            "FFmpeg was not found on PATH. Install FFmpeg before processing audio."
        )
    return ffmpeg


def require_ffprobe() -> str:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise FFmpegNotFoundError(
            "FFprobe was not found on PATH. Install FFmpeg before processing audio."
        )
    return ffprobe


@dataclass(frozen=True)
class AudioWaveformPreview:
    duration_seconds: float
    peaks: tuple[float, ...]


def normalize_to_wav(
    input_path: Path,
    output_path: Path,
    sample_rate: int = 44_100,
    clip_range: AudioClipRange | None = None,
) -> Path:
    """Convert any FFmpeg-readable audio file into a stereo PCM WAV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        build_normalize_command(require_ffmpeg(), input_path, output_path, sample_rate, clip_range),
        check=True,
    )
    return output_path


def probe_audio_duration(input_path: Path) -> float:
    completed = subprocess.run(
        build_duration_command(require_ffprobe(), input_path),
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(completed.stdout or "{}")
    duration = data.get("format", {}).get("duration")
    if duration is None:
        raise ValueError(f"Could not read audio duration for {input_path}")
    return max(0.0, float(duration))


def load_waveform_preview(input_path: Path, max_points: int = 900) -> AudioWaveformPreview:
    duration = probe_audio_duration(input_path)
    if duration <= 0:
        return AudioWaveformPreview(duration, ())
    sample_rate = _waveform_sample_rate(duration, max_points)
    completed = subprocess.run(
        build_waveform_command(require_ffmpeg(), input_path, sample_rate),
        check=True,
        capture_output=True,
    )
    samples = array("h")
    samples.frombytes(completed.stdout)
    if not samples:
        return AudioWaveformPreview(duration, ())
    if sys.byteorder != "little":
        samples.byteswap()
    bucket_size = max(1, len(samples) // max(1, max_points))
    peaks: list[float] = []
    peak_ceiling = 32768.0
    for index in range(0, len(samples), bucket_size):
        bucket = samples[index : index + bucket_size]
        peaks.append(min(1.0, max(abs(value) for value in bucket) / peak_ceiling))
    return AudioWaveformPreview(duration, tuple(peaks[:max_points]))


def build_normalize_command(
    ffmpeg: str,
    input_path: Path,
    output_path: Path,
    sample_rate: int = 44_100,
    clip_range: AudioClipRange | None = None,
) -> list[str]:
    command = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
    ]
    if clip_range is not None:
        command.extend(["-ss", _format_seconds(clip_range.start_seconds)])
    command.extend(["-i", str(input_path)])
    if clip_range is not None:
        command.extend(["-t", _format_seconds(clip_range.duration_seconds)])
    command.extend(
        [
            "-vn",
            "-ac",
            "2",
            "-ar",
            str(sample_rate),
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )
    return command


def build_duration_command(ffprobe: str, input_path: Path) -> list[str]:
    return [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(input_path),
    ]


def build_waveform_command(ffmpeg: str, input_path: Path, sample_rate: int) -> list[str]:
    return [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "s16le",
        "pipe:1",
    ]


def _waveform_sample_rate(duration_seconds: float, max_points: int) -> int:
    target_samples = max(1, max_points) * 120
    return max(40, min(2000, int(target_samples / max(duration_seconds, 1.0))))


def _format_seconds(seconds: float) -> str:
    return f"{seconds:.6f}".rstrip("0").rstrip(".")
