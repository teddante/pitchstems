from pitchstems.scale_preview import scale_preview_notes, scale_preview_pitches


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


def test_scale_preview_notes_use_short_sequential_events() -> None:
    notes = scale_preview_notes("C major", ["C", "D"], "up")

    assert [note.pitch for note in notes] == [60, 62, 72]
    assert notes[0].start == 0.0
    assert notes[1].start > notes[0].end
    assert {note.stem for note in notes} == {"scale-preview"}
