from pitchstems.editor_project import ChordRegion
from pitchstems.editor_review_target import (
    review_range_text,
    review_ranges,
    review_ranges_brief_text,
    review_ranges_detail_text,
    review_ranges_total_seconds,
    single_review_range,
)


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


def test_review_range_text_formats_bounds() -> None:
    assert review_range_text((1.25, 65.5)) == "00:01.250 - 01:05.500"


def test_review_ranges_brief_text_summarizes_single_or_multiple_ranges() -> None:
    assert review_ranges_brief_text([(1.0, 2.0)]) == "00:01.000 - 00:02.000"
    assert review_ranges_brief_text([(1.0, 2.5), (4.0, 5.0)]) == "2 ranges, 2.50s total"


def test_review_ranges_detail_text_lists_ranges_and_total_duration() -> None:
    ranges = [(1.0, 2.5), (4.0, 5.0)]

    assert review_ranges_total_seconds(ranges) == 2.5
    assert (
        review_ranges_detail_text(ranges)
        == "2 ranges (2.500 sec total): 00:01.000 - 00:02.500, 00:04.000 - 00:05.000"
    )
