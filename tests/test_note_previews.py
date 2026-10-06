from pitchstems.note_previews import (
    chord_preview_notes,
    chord_preview_pitches,
    scale_preview_notes,
    scale_preview_pitches,
    single_note_preview_notes,
)


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


def test_chord_preview_pitches_fill_selected_preview_range() -> None:
    assert chord_preview_pitches("C", ["C", "E", "G"], low_pitch=48, high_pitch=67) == [48, 52, 55, 60, 64, 67]


def test_chord_preview_notes_use_official_preview_envelope() -> None:
    notes = chord_preview_notes("C/E", ["C", "E", "G"])

    assert [note.pitch for note in notes] == [40, 48, 52, 55]
    assert {note.stem for note in notes} == {"official-chord"}
    assert {note.start for note in notes} == {0.0}
    assert {note.end for note in notes} == {1.45}
    assert {note.velocity for note in notes} == {92}


def test_scale_preview_pitches_run_up_and_down_by_default() -> None:
    assert scale_preview_pitches("C major", ["C", "D", "E"]) == [60, 62, 64, 72, 64, 62, 60]


def test_scale_preview_pitches_support_up_and_down_patterns() -> None:
    notes = ["C", "D", "E"]

    assert scale_preview_pitches("C major", notes, "up") == [60, 62, 64, 72]
    assert scale_preview_pitches("C major", notes, "down") == [72, 64, 62, 60]


def test_scale_preview_random_pattern_is_deterministic_and_short() -> None:
    notes = ["C", "D", "E", "F", "G"]

    first = scale_preview_pitches("C major", notes, "random")
    second = scale_preview_pitches("C major", notes, "random")

    assert first == second
    assert 6 <= len(first) <= 12
    assert set(first) <= {60, 62, 64, 65, 67}


def test_scale_preview_pitches_use_selected_preview_range() -> None:
    notes = ["C", "D", "E"]

    assert scale_preview_pitches("C major", notes, "up", low_pitch=48, high_pitch=64) == [48, 50, 52, 60, 62, 64]


def test_scale_preview_notes_use_short_sequential_events() -> None:
    notes = scale_preview_notes("C major", ["C", "D"], "up")

    assert [note.pitch for note in notes] == [60, 62, 72]
    assert notes[0].start == 0.0
    assert notes[1].start > notes[0].end
    assert {note.stem for note in notes} == {"scale-preview"}


def test_single_note_preview_notes_clamp_pitch_and_use_short_envelope() -> None:
    low = single_note_preview_notes(-12)[0]
    high = single_note_preview_notes(140)[0]

    assert low.pitch == 0
    assert high.pitch == 127
    assert low.stem == "note-preview"
    assert low.start == 0.0
    assert low.end == 0.55
    assert low.velocity == 96
