from pitchstems.chord_preview import chord_preview_notes, chord_preview_pitches


def test_chord_preview_pitches_stack_notes_upward_from_c3() -> None:
    assert chord_preview_pitches("G", ["G", "B", "D"]) == [55, 59, 62]


def test_chord_preview_pitches_raise_repeated_or_wrapped_notes() -> None:
    assert chord_preview_pitches("Csus2", ["C", "D", "G", "C"]) == [48, 50, 55, 60]


def test_chord_preview_pitches_insert_slash_chord_bass() -> None:
    assert chord_preview_pitches("C/E", ["C", "E", "G"]) == [40, 48, 52, 55]


def test_chord_preview_pitches_accept_preview_bass_override() -> None:
    assert chord_preview_pitches("C", ["C", "E", "G"], bass_name="E") == [40, 48, 52, 55]


def test_chord_preview_pitches_voice_selected_top_note() -> None:
    assert chord_preview_pitches("C", ["C", "E", "G"], top_name="E") == [55, 60, 64]


def test_chord_preview_pitches_ignore_top_note_outside_chord() -> None:
    assert chord_preview_pitches("C", ["C", "E", "G"], top_name="D") == [48, 52, 55]


def test_chord_preview_pitches_support_flat_names() -> None:
    assert chord_preview_pitches("Gb", ["Gb", "Bb", "Db"]) == [54, 58, 61]


def test_chord_preview_notes_use_official_preview_envelope() -> None:
    notes = chord_preview_notes("C/E", ["C", "E", "G"])

    assert [note.pitch for note in notes] == [40, 48, 52, 55]
    assert {note.stem for note in notes} == {"official-chord"}
    assert {note.start for note in notes} == {0.0}
    assert {note.end for note in notes} == {1.45}
    assert {note.velocity for note in notes} == {92}
