from __future__ import annotations

from dataclasses import dataclass
from typing import Any


MIN_CLIP_SECONDS = 0.05


@dataclass(frozen=True)
class AudioClipRange:
    start_seconds: float
    end_seconds: float

    def __post_init__(self) -> None:
        start = float(self.start_seconds)
        end = float(self.end_seconds)
        if start < 0:
            raise ValueError("Clip start must be zero or later.")
        if end - start < MIN_CLIP_SECONDS:
            raise ValueError("Clip range is too short.")
        object.__setattr__(self, "start_seconds", start)
        object.__setattr__(self, "end_seconds", end)

    @property
    def duration_seconds(self) -> float:
        return self.end_seconds - self.start_seconds

    def clamped(self, duration_seconds: float) -> AudioClipRange | None:
        return clamp_clip_range(self.start_seconds, self.end_seconds, duration_seconds)

    def to_manifest(self) -> dict[str, float]:
        return {
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "duration_seconds": self.duration_seconds,
        }


def clamp_clip_range(
    start_seconds: float,
    end_seconds: float,
    duration_seconds: float,
) -> AudioClipRange | None:
    duration = max(0.0, float(duration_seconds))
    start = max(0.0, min(float(start_seconds), duration))
    end = max(0.0, min(float(end_seconds), duration))
    if end < start:
        start, end = end, start
    if end - start < MIN_CLIP_SECONDS:
        return None
    if start <= 0.0 and end >= duration:
        return None
    return AudioClipRange(start, end)


def clip_range_from_manifest(value: Any) -> AudioClipRange | None:
    if not isinstance(value, dict):
        return None
    try:
        return AudioClipRange(
            start_seconds=float(value["start_seconds"]),
            end_seconds=float(value["end_seconds"]),
        )
    except (KeyError, TypeError, ValueError):
        return None
