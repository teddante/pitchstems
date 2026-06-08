from __future__ import annotations

from dataclasses import dataclass


EMPTY_EDITOR_SUMMARY = "Run separation + MIDI to build an editor timeline."


@dataclass(frozen=True)
class EditorSummaryModel:
    track_count: int
    note_count: int
    duration_seconds: float

    @property
    def has_timeline(self) -> bool:
        return self.track_count > 0 or self.note_count > 0 or self.duration_seconds > 0

    @property
    def fit_song_enabled(self) -> bool:
        return self.has_timeline

    @property
    def summary(self) -> str:
        if not self.has_timeline:
            return EMPTY_EDITOR_SUMMARY
        minutes = int(self.duration_seconds // 60)
        seconds = int(self.duration_seconds % 60)
        return (
            f"Editor timeline: {self.track_count} tracks, {self.note_count} notes, "
            f"{minutes}:{seconds:02d}."
        )
