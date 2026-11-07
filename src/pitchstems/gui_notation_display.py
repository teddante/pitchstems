from __future__ import annotations

from pitchstems.chord_naming import (
    chord_bass_name_for_label,
    chord_tones_for_label,
    display_chord_label,
)
from pitchstems.harmony_inspector import (
    resolve_notation_preference,
)
from pitchstems.notation import (
    display_scale_candidate_label,
    display_scale_candidate_notes,
    display_theory_note_names,
    midi_note_name,
    pitch_class_for_name,
    pitch_class_name,
)

class NotationDisplayMixin:
    def selected_notation_preference(self) -> str:
        return self.notation_spelling.currentData() or "auto"

    def resolved_notation_preference(self, chord_label: str | None = None) -> str:
        return resolve_notation_preference(
            self.selected_notation_preference(),
            self.current_theory_analysis.label if self.current_theory_analysis else None,
            chord_label,
        )

    def display_chord(self, label: str | None) -> str:
        if not label:
            return "No clear chord"
        return display_chord_label(label, self.resolved_notation_preference(label))

    def display_chord_tones(self, label: str) -> list[str]:
        return chord_tones_for_label(label, self.resolved_notation_preference(label))

    def display_chord_bass(self, label: str) -> str | None:
        return chord_bass_name_for_label(label, self.resolved_notation_preference(label))

    def display_note_name(self, pitch: int) -> str:
        return midi_note_name(pitch, self.resolved_notation_preference())

    def display_pitch_class_name(self, pitch_class: int) -> str:
        return pitch_class_name(pitch_class, self.resolved_notation_preference())

    def display_weighted_note_name(self, note_name: str) -> str:
        pitch_class = pitch_class_for_name(note_name)
        if pitch_class is None:
            return note_name
        return self.display_pitch_class_name(pitch_class)

    def display_theory_note_names(self, note_names: list[str]) -> list[str]:
        return display_theory_note_names(note_names, self.display_pitch_class_name)

    def display_scale_candidate_label(self, candidate) -> str:
        return display_scale_candidate_label(candidate, self.selected_notation_preference())

    def display_scale_candidate_notes(self, candidate) -> list[str]:
        return display_scale_candidate_notes(candidate, self.selected_notation_preference())
