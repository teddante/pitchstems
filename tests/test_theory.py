from pitchstems.editor_project import ChordRegion, NoteEvent
from pitchstems.chord_gap_analysis import analyze_chord_gap as analyze_gap_from_module
from pitchstems.scale_analysis import analyze_theory_region as analyze_theory_from_module
from pitchstems.theory import (
    SCALE_REGISTRY,
    analyze_chord_gap,
    analyze_theory_region,
    chord_gap_report,
    contained_chords_for_scale,
    searchable_scale_labels,
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
    assert "Chromatic" in names
    assert "Enigmatic" in names
    assert "Raga Bhairav" in names


def test_extracted_theory_modules_expose_core_entry_points() -> None:
    notes = [_note(0.0, 1.0, 60)]

    assert analyze_theory_from_module(notes, [], 0.0, 1.0).candidates
    assert analyze_gap_from_module([], [], 0.0, 1.0).suggestions == []


def test_generated_modes_keep_intervals_relative_to_each_mode_root() -> None:
    scales = {scale.name: scale for scale in SCALE_REGISTRY}

    assert scales["Dorian"].intervals == (0, 2, 3, 5, 7, 9, 10)
    assert scales["Phrygian dominant"].intervals == (0, 1, 4, 5, 7, 8, 10)
    assert scales["Bebop dominant"].intervals == (0, 2, 4, 5, 7, 9, 10, 11)


def test_contained_chords_for_major_scale_include_diatonic_triads_and_sevenths() -> None:
    scales = {scale.name: scale for scale in SCALE_REGISTRY}
    chords = contained_chords_for_scale(0, scales["Ionian"])
    labels = {chord.label for chord in chords}

    assert {"C", "Dm", "Em", "F", "G", "Am", "Bdim"} <= labels
    assert {"Cmaj7", "Dm7", "G7", "Bm7b5"} <= labels


def test_contained_chords_for_blues_scale_use_same_chord_vocabulary() -> None:
    scales = {scale.name: scale for scale in SCALE_REGISTRY}
    chords = contained_chords_for_scale(0, scales["Minor blues"])
    labels = {chord.label for chord in chords}

    assert "Cm" in labels
    assert "Csus4" in labels
    assert all(set(chord.pitch_classes) <= {0, 3, 5, 6, 7, 10} for chord in chords)


def test_searchable_scale_labels_include_all_roots_and_registry_entries() -> None:
    rows = searchable_scale_labels()
    labels = {label for label, _root, _scale in rows}

    assert len(rows) == len(SCALE_REGISTRY) * 12
    assert "C major" in labels
    assert "C Minor blues" in labels


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


def test_progression_roman_numerals_preserve_inversions_and_suffixes() -> None:
    notes = [
        _note(0.0, 4.0, 48, 112),  # C bass centre
        _note(0.0, 4.0, 60, 100),  # C
        _note(0.0, 4.0, 62, 80),  # D
        _note(0.0, 4.0, 64, 92),  # E
        _note(0.0, 4.0, 65, 78),  # F
        _note(0.0, 4.0, 67, 94),  # G
        _note(0.0, 4.0, 69, 82),  # A
        _note(0.0, 4.0, 71, 84),  # B
    ]
    chords = [
        ChordRegion(0.0, 1.0, "C/E", 1.0),
        ChordRegion(1.0, 2.0, "G7/B", 1.0),
        ChordRegion(2.0, 3.0, "Cadd9/D", 1.0),
    ]

    analysis = analyze_theory_region(notes, chords, 0.0, 4.0)

    assert analysis.label == "C major"
    assert analysis.progression is not None
    assert analysis.progression.roman_numerals == ["I6", "V65", "Iadd9/D"]


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


def test_theory_analysis_can_identify_chromatic_collection() -> None:
    notes = [
        _note(0.0, 1.0, 60 + offset, 90)
        for offset in range(12)
    ]

    analysis = analyze_theory_region(notes, [], 0.0, 1.0)

    assert analysis.label == "C Chromatic"
    assert analysis.candidates[0].scale.intervals == tuple(range(12))
    assert analysis.candidates[0].pitch_fit == 1.0


def test_theory_analysis_requires_forced_pitch_classes() -> None:
    notes = [
        _note(0.0, 1.0, 60, 100),
        _note(0.0, 1.0, 62, 90),
        _note(0.0, 1.0, 64, 90),
        _note(0.0, 1.0, 67, 90),
        _note(0.0, 1.0, 69, 90),
    ]

    analysis = analyze_theory_region(notes, [], 0.0, 1.0, required_pitch_classes={6})

    assert analysis.candidates
    assert all(
        6 in {(candidate.root + interval) % 12 for interval in candidate.scale.intervals}
        for candidate in analysis.candidates
    )


def test_theory_analysis_rejects_excluded_pitch_classes() -> None:
    notes = [
        _note(0.0, 1.0, 60, 100),
        _note(0.0, 1.0, 62, 90),
        _note(0.0, 1.0, 64, 90),
        _note(0.0, 1.0, 65, 90),
        _note(0.0, 1.0, 67, 90),
        _note(0.0, 1.0, 69, 90),
        _note(0.0, 1.0, 71, 90),
    ]

    analysis = analyze_theory_region(notes, [], 0.0, 1.0, excluded_pitch_classes={5})

    assert analysis.candidates
    assert all(
        5 not in {(candidate.root + interval) % 12 for interval in candidate.scale.intervals}
        for candidate in analysis.candidates
    )


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
    assert "Aliases:" in report
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
    assert analysis.suggestions[0].pitch_class_movement > 0
    assert analysis.suggestions[0].theory_fit > 0


def test_chord_gap_report_explains_gap_formula_terms() -> None:
    chords = [
        ChordRegion(0.0, 1.0, "C", 1.0),
        ChordRegion(2.0, 3.0, "G", 1.0),
    ]

    report = chord_gap_report(analyze_chord_gap([], chords, 1.0, 2.0))

    assert "Chord Gap Suggestions" in report
    assert "Pitch-class movement uses minimum distance" in report
    assert "Ranking rule:" in report


def test_theory_helpers_expose_gap_support_functions() -> None:
    from pitchstems.editor_models import ChordRegion as SharedChordRegion
    from pitchstems.editor_models import NoteEvent as SharedNoteEvent
    from pitchstems.theory_helpers import (
        candidate_common_tones,
        next_chord,
        previous_chord,
        region_energy,
        report_time,
    )

    chords = [
        SharedChordRegion(0.0, 1.0, "C", 0.9),
        SharedChordRegion(2.0, 3.0, "G", 0.9),
    ]
    notes = [SharedNoteEvent("piano", 1.25, 1.75, 60, 100)]

    assert previous_chord(chords, 1.5) == chords[0]
    assert next_chord(chords, 1.5) == chords[1]
    assert region_energy(notes, 1.0, 2.0) > 0.0
    assert candidate_common_tones({0, 4, 7}, chords[0], chords[1]) > 0.0
    assert report_time(65.0) == "01:05.000"


def test_theory_helpers_count_slash_bass_as_sounding_tone() -> None:
    from pitchstems.editor_models import ChordRegion as SharedChordRegion
    from pitchstems.theory_helpers import candidate_common_tones

    chord = SharedChordRegion(0.0, 1.0, "C/D", 0.9)

    assert candidate_common_tones({2}, chord, None) > 0.0


def _note(start: float, end: float, pitch: int, velocity: int = 100) -> NoteEvent:
    return NoteEvent(
        stem="piano",
        start=start,
        end=end,
        pitch=pitch,
        velocity=velocity,
    )
