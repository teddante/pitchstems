from __future__ import annotations

import contextlib
import math
import os
import wave
from array import array
from pathlib import Path

from pitchstems.editor_project import NoteEvent


def render_midi_preview(
    stem: str,
    notes: list[NoteEvent],
    output_dir: Path,
    duration: float,
    sample_rate: int = 11_025,
) -> Path | None:
    stem_notes = [note for note in notes if note.stem.lower() == stem.lower()]
    if not stem_notes:
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{stem}_midi_preview.wav"
    if _valid_wav(output_path):
        return output_path
    sample_count = max(1, int((duration + 0.25) * sample_rate))
    samples = array("f", [0.0]) * sample_count

    for note in stem_notes:
        _add_note(samples, note, sample_rate)

    peak = max((abs(sample) for sample in samples), default=0.0)
    if peak <= 0:
        return None
    scale = min(0.92 / peak, 1.0)
    pcm = array("h", (int(max(-1.0, min(1.0, sample * scale)) * 32767) for sample in samples))

    _write_wav_atomic(output_path, pcm, sample_rate)
    return output_path


def render_note_preview(
    name: str,
    notes: list[NoteEvent],
    output_dir: Path,
    duration: float = 1.6,
    sample_rate: int = 22_050,
) -> Path | None:
    if not notes:
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(character if character.isalnum() or character in "-_" else "_" for character in name)
    output_path = output_dir / f"{safe_name}.wav"
    sample_count = max(1, int((duration + 0.15) * sample_rate))
    samples = array("f", [0.0]) * sample_count

    for note in notes:
        _add_note(samples, note, sample_rate)

    peak = max((abs(sample) for sample in samples), default=0.0)
    if peak <= 0:
        return None
    scale = min(0.92 / peak, 1.0)
    pcm = array("h", (int(max(-1.0, min(1.0, sample * scale)) * 32767) for sample in samples))

    _write_wav_atomic(output_path, pcm, sample_rate)
    return output_path


def _write_wav_atomic(output_path: Path, pcm: array, sample_rate: int) -> None:
    temporary = output_path.with_name(f".{output_path.name}.{os.getpid()}.tmp")
    try:
        with wave.open(str(temporary), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(pcm.tobytes())
        temporary.replace(output_path)
    finally:
        with contextlib.suppress(OSError):
            if temporary.exists():
                temporary.unlink()


def _valid_wav(path: Path) -> bool:
    if not path.exists():
        return False
    with contextlib.suppress(OSError, wave.Error, EOFError):
        with wave.open(str(path), "rb") as wav:
            return wav.getnframes() > 0 and wav.getframerate() > 0
    return False


def _add_note(samples: array, note: NoteEvent, sample_rate: int) -> None:
    start = max(0, int(note.start * sample_rate))
    end = min(len(samples), max(start + 1, int(note.end * sample_rate)))
    frequency = 440.0 * (2 ** ((note.pitch - 69) / 12))
    phase_step = (2 * math.pi * frequency) / sample_rate
    gain = min(0.22, max(0.02, note.velocity / 127 * 0.14))
    attack = max(1, int(0.01 * sample_rate))
    release = max(1, int(0.04 * sample_rate))

    for index in range(start, end):
        offset = index - start
        remaining = end - index
        envelope = min(1.0, offset / attack, remaining / release)
        # A soft two-oscillator preview is clearer than a bare sine without becoming a full synth.
        value = (
            math.sin(phase_step * offset) * 0.82
            + math.sin(phase_step * 2 * offset) * 0.18
        )
        samples[index] += value * gain * max(0.0, envelope)
