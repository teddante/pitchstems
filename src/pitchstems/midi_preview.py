from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import wave
from array import array
from pathlib import Path

from pitchstems.editor_project import NoteEvent


_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "CLOCK$",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


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
    output_path = midi_preview_path(stem, output_dir)
    metadata = _preview_metadata(stem, stem_notes, duration, sample_rate)
    metadata_path = _metadata_path(output_path)
    if valid_preview_wav(output_path) and _valid_metadata(metadata_path, metadata):
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
    _write_metadata_atomic(metadata_path, metadata)
    return output_path


def midi_preview_path(stem: str, output_dir: Path) -> Path:
    return output_dir / f"{_safe_preview_name(stem, fallback='stem')}_midi_preview.wav"


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
    safe_name = _safe_preview_name(name)
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


def _write_metadata_atomic(path: Path, metadata: dict) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")
        temporary.replace(path)
    finally:
        with contextlib.suppress(OSError):
            if temporary.exists():
                temporary.unlink()


def valid_preview_wav(path: Path) -> bool:
    if not path.exists():
        return False
    with contextlib.suppress(OSError, wave.Error, EOFError), wave.open(str(path), "rb") as wav:
        return wav.getnframes() > 0 and wav.getframerate() > 0
    return False


def _metadata_path(output_path: Path) -> Path:
    return output_path.with_suffix(f"{output_path.suffix}.json")


def _valid_metadata(path: Path, expected: dict) -> bool:
    with contextlib.suppress(OSError, json.JSONDecodeError):
        return json.loads(path.read_text(encoding="utf-8")) == expected
    return False


def _safe_preview_name(name: str, fallback: str = "preview", max_length: int = 80) -> str:
    safe = "".join(character if character.isalnum() or character in "-_" else "_" for character in name)
    safe = safe.strip("._-")[:max_length].rstrip("._-")
    if not safe:
        safe = fallback
    if safe.upper() in _WINDOWS_RESERVED_NAMES:
        safe = f"{fallback}_{safe}"
    return safe


def _preview_metadata(
    stem: str,
    notes: list[NoteEvent],
    duration: float,
    sample_rate: int,
) -> dict:
    return {
        "format": "pitchstems-midi-preview",
        "version": 1,
        "stem": stem,
        "duration": round(duration, 6),
        "sample_rate": sample_rate,
        "note_count": len(notes),
        "note_digest": _note_digest(notes),
    }


def _note_digest(notes: list[NoteEvent]) -> str:
    digest = hashlib.sha256()
    for note in sorted(notes, key=lambda item: (item.start, item.end, item.pitch, item.velocity)):
        digest.update(
            f"{note.start:.6f}|{note.end:.6f}|{note.pitch}|{note.velocity}\n".encode("ascii")
        )
    return digest.hexdigest()


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
