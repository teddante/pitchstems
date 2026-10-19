import subprocess
from pathlib import Path

import pytest

from pitchstems import audio
from pitchstems.audio import build_normalize_command, build_waveform_command
from pitchstems.audio_clip import AudioClipRange


def test_normalize_command_preserves_full_file_defaults() -> None:
    command = build_normalize_command("ffmpeg", Path("source.mp3"), Path("out.wav"))

    assert command == [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        "source.mp3",
        "-vn",
        "-ac",
        "2",
        "-ar",
        "44100",
        "-c:a",
        "pcm_s16le",
        "out.wav",
    ]


def test_normalize_command_adds_clip_seek_and_duration() -> None:
    command = build_normalize_command(
        "ffmpeg",
        Path("source.mp3"),
        Path("out.wav"),
        clip_range=AudioClipRange(12.5, 42.75),
    )

    assert command[5:10] == ["-ss", "12.5", "-i", "source.mp3", "-t"]
    assert command[10] == "30.25"


def test_waveform_command_decodes_low_rate_mono_samples_to_stdout() -> None:
    command = build_waveform_command("ffmpeg", Path("source.wav"), 400)

    assert command[-7:] == ["-ac", "1", "-ar", "400", "-f", "s16le", "pipe:1"]


def test_normalize_to_wav_reports_ffmpeg_stderr(monkeypatch, tmp_path) -> None:
    def fake_run(command, **kwargs):
        assert kwargs["creationflags"] == audio.NO_CONSOLE_WINDOW
        return subprocess.CompletedProcess(command, 1, b"", b"header\nInvalid data found when processing input\n")

    monkeypatch.setattr(audio, "require_ffmpeg", lambda: "C:/tools/ffmpeg.exe")
    monkeypatch.setattr(audio.subprocess, "run", fake_run)

    with pytest.raises(audio.AudioToolError, match=r"ffmpeg failed \(exit 1\): header Invalid data"):
        audio.normalize_to_wav(tmp_path / "in.mp3", tmp_path / "out.wav")
