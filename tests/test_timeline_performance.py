from pitchstems.editor_models import NoteEvent
from pitchstems.editor_query import NoteIndex


def test_note_index_returns_correct_dense_active_notes() -> None:
    notes = [
        NoteEvent(
            stem="piano",
            start=index * 0.01,
            end=index * 0.01 + 0.5,
            pitch=60 + index % 24,
            velocity=80,
        )
        for index in range(10_000)
    ]
    index = NoteIndex(notes)

    active = index.active_at(50.0)

    assert active
    assert all(note.start <= 50.0 < note.end for note in active)
