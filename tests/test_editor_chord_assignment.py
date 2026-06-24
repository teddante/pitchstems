from pitchstems.editor_chord_assignment import chord_assignment_ranges, chord_assignment_target_text
from pitchstems.editor_project import ChordRegion


def test_chord_assignment_ranges_prefer_explicit_selection() -> None:
    selected = ChordRegion(4.0, 5.0, "G", 0.8)

    assert chord_assignment_ranges([(1.0, 2.0), (1.5, 3.0)], selected) == [(1.0, 3.0)]


def test_chord_assignment_ranges_fall_back_to_selected_chord() -> None:
    selected = ChordRegion(4.0, 5.0, "G", 0.8)

    assert chord_assignment_ranges([], selected) == [(4.0, 5.0)]
    assert chord_assignment_target_text([(4.0, 5.0)], selected) == "selected chord"


def test_chord_assignment_target_text_describes_ranges() -> None:
    assert chord_assignment_target_text([(1.0, 2.0)], None) == "00:01.000 - 00:02.000"
    assert chord_assignment_target_text([(1.0, 2.0), (3.0, 4.0)], None) == "2 ranges"
