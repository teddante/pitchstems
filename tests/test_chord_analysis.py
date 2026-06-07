from __future__ import annotations

from pitchstems.chord_analysis import (
    analyze_chord,
    chord_tones_for_label,
    detect_chords,
    midi_note_name,
)


def test_chord_analysis_module_exposes_core_chord_helpers() -> None:
    assert analyze_chord([60, 64, 67]).label == "C"
    assert chord_tones_for_label("F#7sus4/C#") == ["F#", "B", "C#", "E"]
    assert midi_note_name(60) == "C4"


def test_detect_chords_returns_shared_chord_region_type() -> None:
    from pitchstems.editor_models import ChordRegion
    from pitchstems.editor_project import NoteEvent

    chords = detect_chords([
        NoteEvent("piano", 0.0, 1.0, 60, 90),
        NoteEvent("piano", 0.0, 1.0, 64, 90),
        NoteEvent("piano", 0.0, 1.0, 67, 90),
    ])

    assert chords
    assert isinstance(chords[0], ChordRegion)
