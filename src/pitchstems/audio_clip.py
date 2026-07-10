from __future__ import annotations

import math
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
        if not math.isfinite(start) or not math.isfinite(end):
            raise ValueError("Clip range must use finite times.")
        if start < 0:
            raise ValueError("Clip start must be zero or later.")
        if end - start < MIN_CLIP_SECONDS:
            raise ValueError("Clip range is too short.")
        object.__setattr__(self, "start_seconds", start)
        object.__setattr__(self, "end_seconds", end)

    @property
    def duration_seconds(self) -> float:
        return self.end_seconds - self.start_seconds

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
    values = (float(start_seconds), float(end_seconds), float(duration_seconds))
    if not all(math.isfinite(value) for value in values):
        return None
    start_value, end_value, duration_value = values
    duration = max(0.0, duration_value)
    start = max(0.0, min(start_value, duration))
    end = max(0.0, min(end_value, duration))
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
