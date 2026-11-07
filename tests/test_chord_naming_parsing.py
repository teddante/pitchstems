from pitchstems.chord_naming import (
    chord_pitch_classes_for_label,
    chord_sounding_pitch_classes_for_label,
    parse_chord_symbol,
)
from pitchstems.notation import spell_chord_tones


def test_unparseable_suffixes_are_rejected() -> None:
    assert parse_chord_symbol("Cxyz") is None
    assert parse_chord_symbol("C7b") is None
    assert parse_chord_symbol("C7b99") is None


def test_altered_dominants_parse_and_respell_their_alterations() -> None:
    symbol = parse_chord_symbol("G7b9")
    assert symbol is not None
    assert symbol.alterations == ("b9",)
    assert 1 in {interval % 12 for interval in symbol.intervals}
    assert spell_chord_tones("G7b9", symbol.intervals)[0] == "G"


def test_omitted_tones_are_removed_from_the_chord_shape() -> None:
    assert chord_pitch_classes_for_label("C7(no5)") == [0, 4, 10]
    assert chord_pitch_classes_for_label("C7(no3)") == [0, 7, 10]


def test_sounding_tones_follow_the_chord_shape() -> None:
    assert chord_sounding_pitch_classes_for_label("C") == [0, 4, 7]
