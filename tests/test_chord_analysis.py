from __future__ import annotations

from pitchstems.chord_analysis import (
    analyze_chord_region,
    analyze_chord_regions,
    analyze_chord,
    chord_tones_for_label,
    detect_chords,
    midi_note_name,
)
from pitchstems.editor_models import NoteEvent


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


def test_chord_naming_module_exposes_public_helpers() -> None:
    from pitchstems.chord_naming import (
        chord_pitch_classes_for_label,
        chord_tones_for_label,
        display_chord_label,
    )

    assert display_chord_label("Cmaj7") == "Cmaj7"
    assert chord_pitch_classes_for_label("Cmaj7") == [0, 4, 7, 11]
    assert chord_tones_for_label("Cmaj7") == ["C", "E", "G", "B"]


def test_split_chord_modules_expose_public_surfaces() -> None:
    from pitchstems.chord_detection import analyze_chord as analyze_from_detection
    from pitchstems.chord_explanation import partial_harmony_hints
    from pitchstems.chord_scoring import ChordScoringOptions

    assert analyze_from_detection([60, 64, 67]).label == "C"
    assert partial_harmony_hints({0, 7})
    assert ChordScoringOptions(weak_note_floor=0.2).weak_note_floor == 0.2


def test_weighted_chord_analysis_keeps_existing_cmaj7_behavior() -> None:
    notes = [
        NoteEvent("piano", 0.0, 1.0, 60, 100),
        NoteEvent("piano", 0.0, 1.0, 64, 90),
        NoteEvent("piano", 0.0, 1.0, 67, 90),
        NoteEvent("piano", 0.0, 1.0, 71, 70),
    ]

    analysis = analyze_chord_region(notes, 0.0, 1.0)

    assert analysis.label == "Cmaj7"
    assert analysis.candidates[0][0] == "Cmaj7"
    assert analysis.candidate_explanations["Cmaj7"]


def test_multi_range_chord_analysis_combines_only_selected_regions() -> None:
    notes = [
        NoteEvent("piano", 0.0, 1.0, 60, 100),
        NoteEvent("piano", 0.0, 1.0, 64, 96),
        NoteEvent("piano", 0.0, 1.0, 67, 92),
        NoteEvent("piano", 1.0, 2.0, 71, 127),
        NoteEvent("piano", 2.0, 3.0, 60, 100),
        NoteEvent("piano", 2.0, 3.0, 64, 96),
        NoteEvent("piano", 2.0, 3.0, 67, 92),
    ]

    combined = analyze_chord_regions(notes, [(0.0, 1.0), (2.0, 3.0)])
    bounded = analyze_chord_region(notes, 0.0, 3.0)

    assert combined.label == "C"
    assert dict(combined.note_weights).get("B") is None
    assert dict(bounded.note_weights)["B"] > 0
