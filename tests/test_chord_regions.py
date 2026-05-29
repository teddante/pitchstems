from pitchstems.chord_regions import merge_chord_ranges


def test_merge_chord_ranges_sorts_and_merges_overlaps() -> None:
    assert merge_chord_ranges([(2.0, 3.0), (0.5, 1.0), (0.8, 2.2)]) == [(0.5, 3.0)]


def test_merge_chord_ranges_ignores_empty_or_reversed_ranges() -> None:
    assert merge_chord_ranges([(1.0, 1.0), (3.0, 2.0), (2.0, 2.5)]) == [(2.0, 2.5)]


def test_merge_chord_ranges_keeps_touching_edges_connected() -> None:
    assert merge_chord_ranges([(0.0, 1.0), (1.0, 2.0), (2.1, 3.0)]) == [
        (0.0, 2.0),
        (2.1, 3.0),
    ]
