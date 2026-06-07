from __future__ import annotations

from pitchstems.editor_models import ChordRegion, NoteEvent


def test_note_event_duration_never_negative() -> None:
    assert NoteEvent("piano", 2.0, 1.25, 60, 90).duration == 0.0
    assert NoteEvent("piano", 1.25, 2.0, 60, 90).duration == 0.75


def test_chord_region_duration_never_negative() -> None:
    assert ChordRegion(3.0, 2.0, "C", 0.8).duration == 0.0
    assert ChordRegion(2.0, 3.5, "C", 0.8).duration == 1.5


def test_note_event_name_uses_default_notation() -> None:
    assert NoteEvent("piano", 0.0, 1.0, 60, 90).name == "C4"
