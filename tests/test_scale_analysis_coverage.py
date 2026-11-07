import pitchstems.scale_analysis as scale_analysis
from pitchstems.editor_models import ChordRegion, NoteEvent
from pitchstems.scale_analysis import (
    SCALE_REGISTRY,
    analyze_theory_at,
    analyze_theory_region,
)


def _notes() -> list[NoteEvent]:
    return [
        NoteEvent("bass", 0.0, 2.0, 48, 100),
        NoteEvent("mel", 0.0, 2.0, 67, 90),
        NoteEvent("mel", 2.0, 4.0, 64, 90),
    ]


def _chords() -> list[ChordRegion]:
    return [ChordRegion(0.0, 2.0, "C", 1.0), ChordRegion(2.0, 4.0, "Am7", 1.0)]


def test_analyze_theory_at_reports_active_evidence() -> None:
    analysis = analyze_theory_at(_notes(), _chords(), 1.0)

    assert analysis.note_weights
    assert analysis.candidates


def test_analyze_theory_at_applies_pitch_class_constraints() -> None:
    analysis = analyze_theory_at(_notes(), _chords(), 1.0, required_pitch_classes={0}, excluded_pitch_classes={6})

    assert analysis.candidates
    assert all(name not in {"F#", "Gb"} for name, _ in analysis.note_weights)


def test_analyze_theory_region_handles_empty_and_inverted_ranges() -> None:
    analysis = analyze_theory_region(_notes(), _chords(), 3.0, 3.0)

    assert analysis.note_weights == []


def test_analyze_theory_region_applies_constraints_over_range() -> None:
    analysis = analyze_theory_region(
        _notes(),
        _chords(),
        0.0,
        4.0,
        required_pitch_classes={0},
        excluded_pitch_classes={6},
    )

    assert analysis.candidates
    assert analysis.candidates[0].root == 0


def test_roman_numerals_cover_inversions_sevenths_and_qualities() -> None:
    scale = SCALE_REGISTRY[0]
    expected = {
        "C": "I",
        "Am": "vi",
        "Bdim": "viidim",
        "G7": "V7",
        "C/E": "I6",
        "Gm/D": "v64",
        "Am7/G": "vi42",
        "Dm7b5": "ii7b5",
        "CmMaj7": "iMaj7",
        "F9": "IV9",
    }

    for label, numeral in expected.items():
        assert scale_analysis._roman_for_chord(label, 0, scale) == numeral, label


def test_major_seventh_uses_roman_capital_m_notation() -> None:
    scale = SCALE_REGISTRY[0]

    assert scale_analysis._roman_for_chord("Cmaj7", 0, scale) == "IM7"
    assert scale_analysis._roman_for_chord("Cmaj9", 0, scale) == "IM9"


def test_roman_for_unparseable_chord_is_placeholder() -> None:
    assert scale_analysis._roman_for_chord("nonsense", 0, SCALE_REGISTRY[0]) == "?"


def test_quality_suffix_without_seventh_strips_sevenths() -> None:
    expected = {
        "7": "",
        "m7": "",
        "maj7": "maj",
        "mMaj7": "Maj",
        "dim7": "dim",
        "m7b5": "7b5",
    }

    for suffix, stripped in expected.items():
        assert scale_analysis._quality_suffix_without_seventh(suffix) == stripped, suffix


def test_minor_and_seventh_helpers_classify_suffixes() -> None:
    assert [scale_analysis._minor_or_diminished_suffix(s) for s in ["m", "maj7", "dim", "m7b5", "", "mMaj7"]] == [
        True,
        False,
        True,
        True,
        False,
        True,
    ]
    assert [scale_analysis._has_seventh_stack(s) for s in ["7", "maj7", "m9", "", "maj", "13"]] == [
        True,
        True,
        True,
        False,
        False,
        True,
    ]


def test_chord_root_totals_and_unparseable_roots() -> None:
    assert scale_analysis._chord_root("Am7") == 9
    assert scale_analysis._chord_root("nonsense") is None
    assert scale_analysis._chord_root_totals(_chords()) == {0: 2.0, 9: 2.0}


def test_root_prominence_is_none_without_evidence() -> None:
    assert scale_analysis._root_prominence({0: 1.0, 7: 0.5}, 0) == 0.5
    assert scale_analysis._root_prominence({}, 0) is None


def test_suggested_note_groups_empty_without_candidate() -> None:
    assert scale_analysis._suggested_note_groups(None, _chords()) == ([], [], [])


def _candidate(score: float = 0.9, center: float = 0.5) -> scale_analysis.ScaleCandidate:
    return scale_analysis.ScaleCandidate(
        label="C Major",
        root=0,
        scale=SCALE_REGISTRY[0],
        notes=["C"],
        score=score,
        pitch_fit=1.0,
        outside_energy=0.0,
        center_strength=center,
        chord_support=1.0,
        evidence_strength=1.0,
        explanation=[],
    )


def test_clear_interpretation_requires_candidate_breadth_centre_and_score() -> None:
    totals = dict.fromkeys(range(5), 1.0)

    assert scale_analysis._has_clear_interpretation(None, totals) is False
    assert scale_analysis._has_clear_interpretation(_candidate(), {0: 1.0}) is False
    assert scale_analysis._has_clear_interpretation(_candidate(center=0.0), totals) is False
    assert scale_analysis._has_clear_interpretation(_candidate(score=0.1), totals) is False
    assert scale_analysis._has_clear_interpretation(_candidate(), totals) is True


def test_scale_evidence_strength_is_fraction_of_scale_tones_observed() -> None:
    assert scale_analysis._scale_evidence_strength(set(), {0}) == 0.0
    assert scale_analysis._scale_evidence_strength({0, 4, 7, 11}, {0, 4}) == 0.5


def test_center_strength_averages_available_prominences() -> None:
    assert scale_analysis._center_strength(0, {}, {}, {}) == 0.0
    assert scale_analysis._center_strength(0, {0: 2.0, 7: 1.0}, {}, {}) == 0.5
    assert scale_analysis._center_strength(0, {0: 1.0, 7: 1.0}, {}, {}) == 0.0
    assert scale_analysis._center_strength(0, {0: 2.0, 7: 1.0}, {0: 2.0, 7: 1.0}, {0: 2.0, 7: 1.0}) == 0.5


def test_chord_support_weights_chords_fully_inside_the_pitch_set() -> None:
    chords = [
        ChordRegion(0.0, 2.0, "C", 1.0),
        ChordRegion(2.0, 4.0, "G", 1.0),
        ChordRegion(4.0, 4.0, "F", 1.0),
        ChordRegion(4.0, 5.0, "nonsense", 1.0),
    ]

    assert scale_analysis._chord_support({0, 4, 7}, []) == 0.0
    assert scale_analysis._chord_support({0, 4, 7}, chords) == 0.5


def test_chord_root_totals_skip_unparseable_labels() -> None:
    chords = [ChordRegion(0.0, 2.0, "C", 1.0), ChordRegion(2.0, 3.0, "nonsense", 1.0)]

    assert scale_analysis._chord_root_totals(chords) == {0: 2.0}


def test_roman_inversions_cover_seventh_chord_bass_positions() -> None:
    C7 = scale_analysis.parse_chord_symbol("C7")
    assert C7 is not None
    assert scale_analysis._roman_inversion_suffix(C7) == ""
    assert scale_analysis._roman_inversion_suffix(scale_analysis.parse_chord_symbol("C7/E")) == "65"
    assert scale_analysis._roman_inversion_suffix(scale_analysis.parse_chord_symbol("C7/G")) == "43"
    assert scale_analysis._roman_inversion_suffix(scale_analysis.parse_chord_symbol("C7/Bb")) == "42"
    assert scale_analysis._roman_inversion_suffix(scale_analysis.parse_chord_symbol("C7/B")) == "/B"
