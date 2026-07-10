from pitchstems.editor_playback import review_playback_loop_range
from pitchstems.editor_project import ChordRegion


def test_review_playback_loop_range_uses_review_target_rules() -> None:
    selected_chord = ChordRegion(3.0, 4.0, "G", 0.8)

    assert review_playback_loop_range([(1.0, 2.0), (1.5, 2.5)], selected_chord) == (1.0, 2.5)
    assert review_playback_loop_range([], selected_chord) == (3.0, 4.0)
    assert review_playback_loop_range([(1.0, 2.0), (3.0, 4.0)], selected_chord) is None
