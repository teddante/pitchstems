from pitchstems.editor_project import ChordRegion
from pitchstems.editor_review_target import review_ranges, single_review_range


def test_review_ranges_prefer_explicit_selection() -> None:
    selected_chord = ChordRegion(3.0, 4.0, "G", 0.8)

    assert review_ranges([(1.0, 2.0), (1.5, 2.5)], selected_chord) == [(1.0, 2.5)]


def test_review_ranges_fall_back_to_selected_chord() -> None:
    selected_chord = ChordRegion(3.0, 4.0, "G", 0.8)

    assert review_ranges([], selected_chord) == [(3.0, 4.0)]


def test_single_review_range_requires_exactly_one_range() -> None:
    assert single_review_range([(1.0, 2.0)]) == (1.0, 2.0)
    assert single_review_range([]) is None
    assert single_review_range([(1.0, 2.0), (3.0, 4.0)]) is None
