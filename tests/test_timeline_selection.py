from pitchstems.timeline_selection import (
    active_selection_range,
    clamp_selection_bounds,
    commit_selection_range,
    merged_selection_ranges,
)


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
