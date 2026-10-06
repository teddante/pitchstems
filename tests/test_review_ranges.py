from pitchstems.editor_models import ChordRegion
from pitchstems.review_ranges import (
    active_selection_range,
    review_range_text,
    chord_assignment_target_text,
    clamp_selection_bounds,
    commit_selection_range,
    merge_ranges,
    merged_selection_ranges,
    review_navigation_chord,
    review_playback_loop_range,
    review_ranges,
    review_ranges_brief_text,
    review_ranges_detail_text,
    review_ranges_total_seconds,
    review_target,
    single_review_range,
)


def test_merge_ranges_sorts_and_merges_overlaps() -> None:
    assert merge_ranges([(2.0, 3.0), (0.5, 1.0), (0.8, 2.2)]) == [(0.5, 3.0)]


def test_merge_ranges_ignores_empty_or_reversed_ranges() -> None:
    assert merge_ranges([(1.0, 1.0), (3.0, 2.0), (2.0, 2.5)]) == [(2.0, 2.5)]


def test_merge_ranges_keeps_touching_edges_connected() -> None:
    assert merge_ranges([(0.0, 1.0), (1.0, 2.0), (2.1, 3.0)]) == [
        (0.0, 2.0),
        (2.1, 3.0),
    ]


def test_clamp_selection_bounds_stays_inside_duration() -> None:
    assert clamp_selection_bounds(-1.0, 12.0, 4.0) == (0.0, 4.0)
    assert clamp_selection_bounds(2.0, 1.0, -1.0) == (0.0, 0.0)


def test_active_selection_range_sorts_and_rejects_tiny_spans() -> None:
    assert active_selection_range(2.0, 1.0) == (1.0, 2.0)
    assert active_selection_range(1.0, 1.01) is None
    assert active_selection_range(None, 2.0) is None


def test_merged_selection_ranges_include_current_drag() -> None:
    assert merged_selection_ranges([(2.0, 3.0), (0.5, 1.0)], (0.8, 2.2)) == [(0.5, 3.0)]


def test_commit_selection_range_replaces_or_adds_ranges() -> None:
    assert commit_selection_range([(0.0, 1.0)], (2.0, 3.0), additive=False) == [(2.0, 3.0)]
    assert commit_selection_range([(0.0, 1.0)], (1.0, 2.0), additive=True) == [(0.0, 2.0)]
    assert commit_selection_range([(0.0, 1.0)], None, additive=False) == []
    assert commit_selection_range([(0.0, 1.0)], None, additive=True) == [(0.0, 1.0)]


def test_review_ranges_prefer_explicit_selection() -> None:
    selected_chord = ChordRegion(3.0, 4.0, "G", 0.8)

    assert review_ranges([(1.0, 2.0), (1.5, 2.5)], selected_chord) == [(1.0, 2.5)]


def test_review_ranges_fall_back_to_selected_chord() -> None:
    selected_chord = ChordRegion(3.0, 4.0, "G", 0.8)

    assert review_ranges([], selected_chord) == [(3.0, 4.0)]


def test_review_target_names_explicit_selection() -> None:
    selected_chord = ChordRegion(3.0, 4.0, "G", 0.8)

    target = review_target([(1.0, 2.0)], selected_chord, 9.0)

    assert target.mode == "selection"
    assert target.heading == "Timeline range"
    assert target.ranges == ((1.0, 2.0),)
    assert target.chord is None


def test_review_target_names_selected_chord_fallback() -> None:
    selected_chord = ChordRegion(3.0, 4.0, "G", 0.8)

    target = review_target([], selected_chord, 9.0)

    assert target.mode == "selected_chord"
    assert target.heading == "Selected chord"
    assert target.single_range == (3.0, 4.0)
    assert target.chord == selected_chord


def test_review_target_names_playhead_without_range_or_chord() -> None:
    target = review_target([], None, 9.0)

    assert target.mode == "playhead"
    assert target.heading == "Playhead"
    assert target.ranges == ()


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


def test_review_navigation_steps_from_selected_chord() -> None:
    chords = [
        ChordRegion(0.0, 1.0, "C", 0.8),
        ChordRegion(1.0, 2.0, "F", 0.8),
        ChordRegion(2.0, 3.0, "G", 0.8),
    ]

    assert review_navigation_chord(chords, chords[1], 9.0, 1) == chords[2]
    assert review_navigation_chord(chords, chords[1], 9.0, -1) == chords[0]


def test_review_navigation_stays_at_edges() -> None:
    chords = [
        ChordRegion(0.0, 1.0, "C", 0.8),
        ChordRegion(1.0, 2.0, "F", 0.8),
    ]

    assert review_navigation_chord(chords, chords[0], 0.0, -1) == chords[0]
    assert review_navigation_chord(chords, chords[-1], 0.0, 1) == chords[-1]


def test_review_navigation_uses_playhead_without_selected_chord() -> None:
    chords = [
        ChordRegion(0.0, 1.0, "C", 0.8),
        ChordRegion(1.5, 2.0, "F", 0.8),
        ChordRegion(3.0, 4.0, "G", 0.8),
    ]

    assert review_navigation_chord(chords, None, 0.5, 1) == chords[0]
    assert review_navigation_chord(chords, None, 2.5, 1) == chords[2]
    assert review_navigation_chord(chords, None, 2.5, -1) == chords[1]


def test_review_navigation_handles_empty_or_zero_direction() -> None:
    chord = ChordRegion(0.0, 1.0, "C", 0.8)

    assert review_navigation_chord([], None, 0.0, 1) is None
    assert review_navigation_chord([chord], None, 0.0, 0) is None


def test_review_playback_loop_range_uses_review_target_rules() -> None:
    selected_chord = ChordRegion(3.0, 4.0, "G", 0.8)

    assert review_playback_loop_range([(1.0, 2.0), (1.5, 2.5)], selected_chord) == (1.0, 2.5)
    assert review_playback_loop_range([], selected_chord) == (3.0, 4.0)
    assert review_playback_loop_range([(1.0, 2.0), (3.0, 4.0)], selected_chord) is None


def test_chord_assignment_ranges_prefer_explicit_selection() -> None:
    selected = ChordRegion(4.0, 5.0, "G", 0.8)

    assert review_ranges([(1.0, 2.0), (1.5, 3.0)], selected) == [(1.0, 3.0)]


def test_chord_assignment_ranges_fall_back_to_selected_chord() -> None:
    selected = ChordRegion(4.0, 5.0, "G", 0.8)

    assert review_ranges([], selected) == [(4.0, 5.0)]
    assert chord_assignment_target_text([(4.0, 5.0)], selected) == "selected chord"


def test_chord_assignment_target_text_describes_ranges() -> None:
    assert chord_assignment_target_text([(1.0, 2.0)], None) == "00:01.000 - 00:02.000"
    assert chord_assignment_target_text([(1.0, 2.0), (3.0, 4.0)], None) == "2 ranges"
