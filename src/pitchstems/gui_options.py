from __future__ import annotations

from pitchstems.transcription import PERCUSSIVE_STEMS


def optional_frequency(value: float) -> float | None:
    return value if value > 0 else None


def default_midi_checked(stem_name: str) -> bool:
    return stem_name.lower() not in {*PERCUSSIVE_STEMS, "wet"}


def device_label(device: str | None, cuda_available: bool) -> str:
    if device == "cpu":
        return "PyTorch CPU (forced)"
    if device:
        return f"PyTorch CUDA ({device})"
    return "PyTorch CUDA (auto)" if cuda_available else "PyTorch CPU (auto fallback)"
