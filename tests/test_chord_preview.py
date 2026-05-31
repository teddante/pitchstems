from pitchstems.chord_preview import chord_preview_pitches


def test_chord_preview_pitches_stack_notes_upward_from_c3() -> None:
    assert chord_preview_pitches("G", ["G", "B", "D"]) == [55, 59, 62]


def test_chord_preview_pitches_raise_repeated_or_wrapped_notes() -> None:
    assert chord_preview_pitches("Csus2", ["C", "D", "G", "C"]) == [48, 50, 55, 60]


def test_chord_preview_pitches_insert_slash_chord_bass() -> None:
    assert chord_preview_pitches("C/E", ["C", "E", "G"]) == [40, 48, 52, 55]


def test_chord_preview_pitches_support_flat_names() -> None:
    assert chord_preview_pitches("Gb", ["Gb", "Bb", "Db"]) == [54, 58, 61]
