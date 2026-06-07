from __future__ import annotations

from pitchstems.chord_analysis import analyze_chord, chord_tones_for_label, midi_note_name


def test_chord_analysis_module_exposes_core_chord_helpers() -> None:
    assert analyze_chord([60, 64, 67]).label == "C"
    assert chord_tones_for_label("F#7sus4/C#") == ["F#", "B", "C#", "E"]
    assert midi_note_name(60) == "C4"
