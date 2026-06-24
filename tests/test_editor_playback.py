from pitchstems.editor_playback import playback_loop_range
from pitchstems.editor_project import ChordRegion


def test_playback_loop_range_prefers_explicit_selection() -> None:
    selected_chord = ChordRegion(3.0, 4.0, "G", 0.8)

    assert playback_loop_range((1.0, 2.0), selected_chord) == (1.0, 2.0)


def test_playback_loop_range_falls_back_to_selected_chord() -> None:
    selected_chord = ChordRegion(3.0, 4.0, "G", 0.8)

    assert playback_loop_range(None, selected_chord) == (3.0, 4.0)


def test_playback_loop_range_allows_no_loop_target() -> None:
    assert playback_loop_range(None, None) is None
