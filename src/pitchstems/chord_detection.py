"""Compatibility exports for chord detection internals.

The implementation still lives in ``pitchstems.chord_analysis`` so public imports
can stabilize before a larger mechanical extraction. Do not add new detection logic
here; move the implementation from ``chord_analysis`` first.
"""

from __future__ import annotations

from pitchstems.chord_analysis import (
    active_notes_at,
    analyze_chord,
    analyze_chord_at,
    analyze_chord_region,
    analyze_chord_regions,
    detect_chords,
    midi_velocity_energy,
)

__all__ = [
    "active_notes_at",
    "analyze_chord",
    "analyze_chord_at",
    "analyze_chord_region",
    "analyze_chord_regions",
    "detect_chords",
    "midi_velocity_energy",
]
