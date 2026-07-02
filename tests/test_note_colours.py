from pitchstems.note_colours import note_colour_map


def test_note_colour_map_rotates_to_root_pitch_class() -> None:
    colours = note_colour_map(["E", "G", "C"], root_pitch_class=0)

    assert list(colours) == [0, 4, 7]
    assert len(set(colours.values())) == 3
