from __future__ import annotations

from pitchstems.transcription import PERCUSSIVE_STEMS, optional_frequency_limit


def optional_frequency(value: float) -> float | None:
    return optional_frequency_limit(value)


def default_midi_checked(stem_name: str) -> bool:
    return stem_name.lower() not in PERCUSSIVE_STEMS


def device_label(device: str | None, cuda_available: bool) -> str:
    if device == "cpu":
        return "PyTorch CPU (forced)"
    if device:
        return f"PyTorch CUDA ({device})"
    return "PyTorch CUDA (auto)" if cuda_available else "PyTorch CPU (auto fallback)"
