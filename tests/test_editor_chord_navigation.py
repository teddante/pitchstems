from pitchstems.editor_chord_navigation import review_navigation_chord
from pitchstems.editor_project import ChordRegion


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
