from __future__ import annotations

from typing import Iterable, TypeVar


T = TypeVar("T")


def percent_text(value: float) -> str:
    return f"{max(0.0, min(1.0, value)):.0%}"


def is_chromatic_candidate(candidate) -> bool:
    scale = getattr(candidate, "scale", None)
    return getattr(scale, "name", "") == "Chromatic"


def visible_scale_candidates(candidates: Iterable[T], *, show_chromatic: bool) -> list[T]:
    if show_chromatic:
        return list(candidates)
    return [candidate for candidate in candidates if not is_chromatic_candidate(candidate)]
