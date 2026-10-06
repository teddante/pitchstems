from dataclasses import dataclass

from pitchstems.chord_naming import (
    chord_bass_name_for_label,
    chord_pitch_classes_for_label,
    chord_sounding_pitch_classes_for_label,
    chord_tones_for_label,
    display_chord_label,
)
from pitchstems.notation import (
    display_scale_candidate_label,
    display_scale_candidate_notes,
    display_theory_note_names,
    percent_text,
    pitch_class_for_name,
    pitch_class_name,
    scale_label,
    spell_scale,
    visible_scale_candidates,
)
from pitchstems.scale_analysis import ScaleCandidate, ScaleDefinition


def test_chord_tones_use_the_chord_root_spelling() -> None:
    assert chord_tones_for_label("F#") == ["F#", "A#", "C#"]
    assert chord_tones_for_label("Gb") == ["Gb", "Bb", "Db"]
    assert chord_tones_for_label("Bb7") == ["Bb", "D", "F", "Ab"]


def test_chord_labels_can_be_respelt_for_display_without_changing_pitch_classes() -> None:
    assert chord_pitch_classes_for_label("F#") == chord_pitch_classes_for_label("Gb")
    assert display_chord_label("F#/C#", "flat") == "Gb/Db"
    assert display_chord_label("Bb/D", "sharp") == "A#/D"


def test_chord_bass_name_for_label_uses_parsed_slash_bass() -> None:
    assert chord_bass_name_for_label("F#/C#", "flat") == "Db"
    assert chord_bass_name_for_label("Bb/D", "sharp") == "D"
    assert chord_bass_name_for_label("Cmaj7") is None


def test_sounding_chord_pitch_classes_keep_slash_bass_semantics() -> None:
    assert chord_pitch_classes_for_label("C/D") == [0, 4, 7]
    assert chord_sounding_pitch_classes_for_label("C/D") == [2, 0, 4, 7]
    assert chord_sounding_pitch_classes_for_label("C/E") == [4, 0, 7]


def test_chord_tones_parse_common_altered_extensions() -> None:
    assert chord_pitch_classes_for_label("C7#9") == [0, 4, 7, 10, 3]
    assert chord_tones_for_label("C7#9") == ["C", "E", "G", "Bb", "D#"]
    assert chord_pitch_classes_for_label("C13b9") == [0, 4, 7, 10, 1, 9]
    assert chord_tones_for_label("C13b9") == ["C", "E", "G", "Bb", "Db", "A"]
    assert chord_tones_for_label("C13#9") == ["C", "E", "G", "Bb", "D#", "A"]
    assert chord_tones_for_label("C7b5") == ["C", "E", "Gb", "Bb"]
    assert chord_tones_for_label("C11#11") == ["C", "E", "G", "Bb", "D", "F#"]
    assert chord_tones_for_label("C13b13") == ["C", "E", "G", "Bb", "D", "Ab"]


def test_heptatonic_scale_spelling_uses_one_letter_per_degree() -> None:
    major = (0, 2, 4, 5, 7, 9, 11)

    assert scale_label(1, major, "Ionian") == "Db major"
    assert spell_scale(1, major) == ["Db", "Eb", "F", "Gb", "Ab", "Bb", "C"]
    assert spell_scale(6, major, "sharp") == ["F#", "G#", "A#", "B", "C#", "D#", "E#"]
    assert spell_scale(6, major, "flat") == ["Gb", "Ab", "Bb", "Cb", "Db", "Eb", "F"]


def test_pitch_class_parser_supports_double_accidentals() -> None:
    assert pitch_class_for_name("C##") == 2
    assert pitch_class_for_name("E##4") == 6
    assert pitch_class_for_name("Dbb") == 0
    assert pitch_class_for_name("Abb3") == 7


@dataclass(frozen=True)
class _Scale:
    name: str


@dataclass(frozen=True)
class _Candidate:
    scale: _Scale


def test_percent_text_clamps_without_ascii_bar() -> None:
    assert percent_text(0.64) == "64%"
    assert percent_text(2.0) == "100%"


def test_visible_scale_candidates_can_hide_chromatic_candidates() -> None:
    chromatic = _Candidate(_Scale("Chromatic"))
    major = _Candidate(_Scale("Ionian"))

    assert visible_scale_candidates([chromatic, major], show_chromatic=False) == [major]
    assert visible_scale_candidates([chromatic, major], show_chromatic=True) == [chromatic, major]


def _candidate(root: int = 1) -> ScaleCandidate:
    return ScaleCandidate(
        label="Db major",
        root=root,
        scale=ScaleDefinition("Ionian", (0, 2, 4, 5, 7, 9, 11), "major"),
        notes=[],
        score=1.0,
        pitch_fit=1.0,
        outside_energy=0.0,
        center_strength=1.0,
        chord_support=1.0,
    )


def test_display_scale_candidate_respects_explicit_notation_preference() -> None:
    candidate = _candidate()

    assert display_scale_candidate_label(candidate, "sharp") == "C# major"
    assert display_scale_candidate_notes(candidate, "sharp") == ["C#", "D#", "E#", "F#", "G#", "A#", "B#"]
    assert display_scale_candidate_label(candidate, "flat") == "Db major"
    assert display_scale_candidate_notes(candidate, "flat") == ["Db", "Eb", "F", "Gb", "Ab", "Bb", "C"]


def test_display_theory_note_names_uses_formatter_for_known_notes() -> None:
    assert display_theory_note_names(
        ["Bb", "C#", "noise"],
        lambda pitch_class: pitch_class_name(pitch_class, "sharp"),
    ) == ["A#", "C#", "noise"]
