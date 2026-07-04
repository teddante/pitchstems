from pitchstems.editor_project import (
    chord_bass_name_for_label,
    chord_pitch_classes_for_label,
    chord_sounding_pitch_classes_for_label,
    chord_tones_for_label,
    display_chord_label,
)
from pitchstems.notation import pitch_class_for_name, scale_label, spell_scale


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
    assert chord_pitch_classes_for_label("C13b9") == [0, 4, 7, 10, 2, 9, 1]
    assert chord_tones_for_label("C7b5") == ["C", "E", "Gb", "Bb"]


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
