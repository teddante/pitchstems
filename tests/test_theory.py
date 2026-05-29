from pitchstems.editor_project import ChordRegion, NoteEvent
from pitchstems.theory import (
    SCALE_REGISTRY,
    analyze_chord_gap,
    analyze_theory_region,
    chord_gap_report,
    theory_analysis_report,
)


def test_scale_registry_includes_common_modal_and_symmetrical_families() -> None:
    names = {scale.name for scale in SCALE_REGISTRY}

    assert len(SCALE_REGISTRY) >= 60
    assert "Ionian" in names
    assert "Dorian" in names
    assert "Harmonic minor" in names
    assert "Phrygian dominant" in names
    assert "Harmonic major" in names
    assert "Melodic minor" in names
    assert "Altered" in names
    assert "Major pentatonic" in names
    assert "Hirajoshi" in names
    assert "Minor blues" in names
    assert "Bebop dominant" in names
    assert "Whole tone" in names
    assert "Diminished half-whole" in names
    assert "Enigmatic" in names
    assert "Raga Bhairav" in names


def test_generated_modes_keep_intervals_relative_to_each_mode_root() -> None:
    scales = {scale.name: scale for scale in SCALE_REGISTRY}

    assert scales["Dorian"].intervals == (0, 2, 3, 5, 7, 9, 10)
    assert scales["Phrygian dominant"].intervals == (0, 1, 4, 5, 7, 8, 10)
    assert scales["Bebop dominant"].intervals == (0, 2, 4, 5, 7, 9, 10, 11)


def test_theory_analysis_separates_pitch_collection_from_tonal_centre() -> None:
    notes = [
        _note(0.0, 4.0, 38, 112),  # D bass centre
        _note(0.0, 4.0, 50, 96),  # D
        _note(0.0, 4.0, 52, 72),  # E
        _note(0.0, 4.0, 53, 88),  # F
        _note(0.0, 4.0, 55, 92),  # G
        _note(0.0, 4.0, 57, 90),  # A
        _note(0.0, 4.0, 59, 68),  # B
        _note(0.0, 4.0, 60, 82),  # C
    ]
    chords = [
        ChordRegion(0.0, 2.0, "Dm7", 1.0),
        ChordRegion(2.0, 4.0, "G", 1.0),
    ]

    analysis = analyze_theory_region(notes, chords, 0.0, 4.0)

    assert analysis.label == "D Dorian"
    assert analysis.candidates[0].notes == ["D", "E", "F", "G", "A", "B", "C"]
    assert "C major" in [candidate.label for candidate in analysis.candidates]
    assert analysis.progression is not None
    assert analysis.progression.roman_numerals == ["i7", "IV"]


def test_theory_analysis_names_harmonic_minor_when_raised_seventh_is_present() -> None:
    notes = [
        _note(0.0, 2.0, 45, 112),  # A
        _note(0.0, 2.0, 47, 80),  # B
        _note(0.0, 2.0, 48, 92),  # C
        _note(0.0, 2.0, 50, 70),  # D
        _note(0.0, 2.0, 52, 90),  # E
        _note(0.0, 2.0, 53, 76),  # F
        _note(0.0, 2.0, 56, 86),  # G#
    ]
    chords = [
        ChordRegion(0.0, 1.0, "Am", 1.0),
        ChordRegion(1.0, 2.0, "E7", 1.0),
    ]

    analysis = analyze_theory_region(notes, chords, 0.0, 2.0)
    labels = [candidate.label for candidate in analysis.candidates[:4]]

    assert "A Harmonic minor" in labels
    assert analysis.progression is not None
    assert analysis.progression.roman_numerals[:2] == ["i", "V7"]


def test_theory_analysis_can_identify_whole_tone_collection() -> None:
    notes = [
        _note(0.0, 1.0, 60, 100),
        _note(0.0, 1.0, 62, 90),
        _note(0.0, 1.0, 64, 90),
        _note(0.0, 1.0, 66, 90),
        _note(0.0, 1.0, 68, 90),
        _note(0.0, 1.0, 70, 90),
    ]

    analysis = analyze_theory_region(notes, [], 0.0, 1.0)

    assert "C Whole tone" in [candidate.label for candidate in analysis.candidates[:3]]


def test_theory_report_explains_evidence_and_formula_terms() -> None:
    notes = [
        _note(0.0, 1.0, 60, 100),
        _note(0.0, 1.0, 64, 90),
        _note(0.0, 1.0, 67, 88),
    ]
    analysis = analyze_theory_region(notes, [ChordRegion(0.0, 1.0, "C", 1.0)], 0.0, 1.0)

    report = theory_analysis_report(analysis)

    assert "MIDI energy model" in report
    assert "Scale / Key / Mode Candidates" in report
    assert "Ranking rule:" in report
    assert "Progression" in report
    assert "Core chord tones" in report


def test_chord_gap_suggestions_prefer_continuity_when_gap_has_no_notes() -> None:
    chords = [
        ChordRegion(0.0, 1.0, "C", 1.0),
        ChordRegion(2.0, 3.0, "G", 1.0),
    ]

    analysis = analyze_chord_gap([], chords, 1.0, 2.0)

    labels = [suggestion.label for suggestion in analysis.suggestions[:2]]
    assert "C" in labels
    assert "G" in labels
    assert analysis.suggestions[0].local_evidence == 1.0
    assert analysis.previous_chord == chords[0]
    assert analysis.next_chord == chords[1]


def test_chord_gap_suggestions_use_local_midi_evidence_inside_gap() -> None:
    notes = [
        _note(1.0, 2.0, 62, 112),  # D
        _note(1.0, 2.0, 65, 100),  # F
        _note(1.0, 2.0, 69, 96),  # A
    ]
    chords = [
        ChordRegion(0.0, 1.0, "C", 1.0),
        ChordRegion(2.0, 3.0, "G", 1.0),
    ]

    analysis = analyze_chord_gap(notes, chords, 1.0, 2.0)

    assert analysis.suggestions[0].label == "Dm"
    assert analysis.suggestions[0].local_evidence > 0.8
    assert analysis.suggestions[0].voice_leading > 0
    assert analysis.suggestions[0].theory_fit > 0


def test_chord_gap_report_explains_gap_formula_terms() -> None:
    chords = [
        ChordRegion(0.0, 1.0, "C", 1.0),
        ChordRegion(2.0, 3.0, "G", 1.0),
    ]

    report = chord_gap_report(analyze_chord_gap([], chords, 1.0, 2.0))

    assert "Chord Gap Suggestions" in report
    assert "Voice-leading uses minimum pitch-class movement" in report
    assert "Ranking rule:" in report


def _note(start: float, end: float, pitch: int, velocity: int = 100) -> NoteEvent:
    return NoteEvent(
        stem="piano",
        start=start,
        end=end,
        pitch=pitch,
        velocity=velocity,
    )
