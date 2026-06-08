from __future__ import annotations

from pitchstems.editor_models import ChordRegion, NoteEvent
from pitchstems.editor_query import ChordIndex, NoteIndex


def test_note_index_returns_notes_active_at_time() -> None:
    notes = [
        NoteEvent("piano", 0.0, 1.0, 60, 90),
        NoteEvent("bass", 2.0, 3.0, 40, 90),
    ]
    index = NoteIndex(notes)
    assert index.active_at(0.5) == [notes[0]]
    assert index.active_at(2.5) == [notes[1]]


def test_chord_index_returns_gap_between_chords() -> None:
    chords = [
        ChordRegion(0.0, 1.0, "C", 0.8),
        ChordRegion(2.0, 3.0, "G", 0.8),
    ]
    index = ChordIndex(chords, duration=4.0)
    assert index.gap_at(1.5) == (1.0, 2.0)
    assert index.gap_at(0.5) is None


def test_chord_index_uses_ordered_starts_for_active_lookup() -> None:
    chords = [
        ChordRegion(0.0, 1.0, "C", 0.9),
        ChordRegion(2.0, 3.0, "G", 0.8),
        ChordRegion(4.0, 5.0, "Am", 0.7),
    ]
    index = ChordIndex(chords, duration=6.0)

    assert index.starts == [0.0, 2.0, 4.0]
    assert index.active_at(2.5) == chords[1]
    assert index.active_at(3.5) is None
    assert index.gap_at(3.5) == (3.0, 4.0)
