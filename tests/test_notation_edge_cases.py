from pitchstems.chord_naming import (
    alternate_chord_names_for_label,
    chord_bass_name_for_label,
    chord_pitch_classes_for_label,
    chord_sounding_pitch_classes_for_label,
    chord_tones_for_label,
    exact_chord_names_for_pitch_classes,
    parse_chord_symbol,
)
from pitchstems.notation import (
    normalized_pitch_class_weights,
    pitch_class_for_name,
    respell_chord_label,
    spell_chord_tones,
    spelling_preference_from_label,
    split_chord_label,
)


def test_pitch_class_for_name_handles_accidentals_and_unknown_letters() -> None:
    assert pitch_class_for_name("C#") == 1
    assert pitch_class_for_name("Bb") == 10
    assert pitch_class_for_name("") is None
    assert pitch_class_for_name("H") is None


def test_normalized_pitch_class_weights_scale_to_the_loudest_class() -> None:
    assert normalized_pitch_class_weights({}) == []
    assert normalized_pitch_class_weights({0: 0.0}) == []
    assert normalized_pitch_class_weights({0: 1.0, 7: 0.5}) == [("C", 1.0), ("G", 0.5)]


def test_unparseable_labels_fall_back_safely() -> None:
    assert split_chord_label("nonsense") is None
    assert respell_chord_label("nonsense") == "nonsense"
    assert spelling_preference_from_label("") == "auto"
    assert spelling_preference_from_label("nonsense") == "auto"
    assert spelling_preference_from_label("Bb") == "flat"
    assert spelling_preference_from_label("F#m") == "sharp"
    assert spell_chord_tones("nonsense", [0, 4, 7]) == ["C", "E", "G"]


def test_chord_helpers_return_empty_results_for_unparseable_labels() -> None:
    assert parse_chord_symbol("nonsense") is None
    assert chord_pitch_classes_for_label("nonsense") == []
    assert chord_sounding_pitch_classes_for_label("nonsense") == []
    assert chord_tones_for_label("nonsense") == []
    assert alternate_chord_names_for_label("nonsense") == []
    assert chord_bass_name_for_label("C") is None


def test_chord_bass_and_pitch_classes_for_slash_chords() -> None:
    assert chord_bass_name_for_label("C/E") == "E"
    assert chord_pitch_classes_for_label("C") == [0, 4, 7]


def test_exact_chord_names_empty_for_empty_pitch_set() -> None:
    assert exact_chord_names_for_pitch_classes(set()) == []
