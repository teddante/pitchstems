from pitchstems.note_preview import single_note_preview_notes


def test_single_note_preview_notes_clamp_pitch_and_use_short_envelope() -> None:
    low = single_note_preview_notes(-12)[0]
    high = single_note_preview_notes(140)[0]

    assert low.pitch == 0
    assert high.pitch == 127
    assert low.stem == "note-preview"
    assert low.start == 0.0
    assert low.end == 0.55
    assert low.velocity == 96
