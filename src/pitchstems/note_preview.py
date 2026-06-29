from __future__ import annotations

from pitchstems.editor_models import NoteEvent


def single_note_preview_notes(pitch: int, duration: float = 0.55) -> list[NoteEvent]:
    return [
        NoteEvent(
            stem="note-preview",
            start=0.0,
            end=duration,
            pitch=max(0, min(127, pitch)),
            velocity=96,
        )
    ]
