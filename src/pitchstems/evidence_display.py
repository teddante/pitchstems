from __future__ import annotations

from typing import Iterable, TypeVar


T = TypeVar("T")


def percent_bar(value: float, width: int = 10) -> str:
    value = max(0.0, min(1.0, value))
    filled = round(value * width)
    return "[" + ("#" * filled) + ("-" * (width - filled)) + "]"


def percent_with_bar(value: float, width: int = 10) -> str:
    return f"{value:.0%} {percent_bar(value, width)}"


def is_chromatic_candidate(candidate) -> bool:
    scale = getattr(candidate, "scale", None)
    return getattr(scale, "name", "") == "Chromatic"


def visible_scale_candidates(candidates: Iterable[T], *, show_chromatic: bool) -> list[T]:
    if show_chromatic:
        return list(candidates)
    return [candidate for candidate in candidates if not is_chromatic_candidate(candidate)]
