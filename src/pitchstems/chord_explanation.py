"""Compatibility exports for chord explanation internals.

The implementation still lives in ``pitchstems.chord_analysis`` so public imports
can stabilize before a larger mechanical extraction. Do not add new explanation
logic here; move the implementation from ``chord_analysis`` first.
"""

from __future__ import annotations

from pitchstems.chord_analysis import (
    _interval_names,
    _interval_quality_name,
    _ordered_pitch_classes,
    partial_harmony_hints,
)

__all__ = [
    "partial_harmony_hints",
    "_interval_names",
    "_interval_quality_name",
    "_ordered_pitch_classes",
]
