from __future__ import annotations

from dataclasses import dataclass

from pitchstems.editor_project import analyze_chord_at, analyze_chord_region
from pitchstems.harmony_inspector import (
    chord_base_pitch_weights as inspector_chord_base_pitch_weights,
    chord_note_constraints as inspector_chord_note_constraints,
    chord_sample_text as inspector_chord_sample_text,
    filtered_chord_analysis_notes as inspector_filtered_chord_analysis_notes,
    harmony_context_key as inspector_harmony_context_key,
    selected_chord_analysis_notes,
)
from pitchstems import harmony_panel
from pitchstems.time_format import format_time


@dataclass
class HarmonyRefreshGate:
    min_interval_seconds: float = 0.25
    last_refresh_seconds: float | None = None

    def should_refresh(self, position_seconds: float, now_seconds: float, force: bool = False) -> bool:
        if force or self.last_refresh_seconds is None:
            self.last_refresh_seconds = now_seconds
            return True
        if now_seconds - self.last_refresh_seconds >= self.min_interval_seconds:
            self.last_refresh_seconds = now_seconds
            return True
        return False


def refresh_current_harmony(window, seconds: float) -> None:
    if window.editor_project is None:
        window.current_chord.setText("Harmony: -")
        window.set_chord_context_text("Sample: -")
        window.chord_list.clear()
        window.refresh_chord_keyboard()
        window.set_theory_analysis(None)
        window.set_gap_analysis(None)
        window.current_harmony_context = None
        window.note_filter_list.clear()
        window.inspect_chord_button.setEnabled(False)
        return
    window.inspect_chord_button.setEnabled(True)
    context = window.chord_context_key(seconds)
    if context != window.chord_note_filter_context:
        window.chord_note_filter_context = context
        window.chord_note_overrides = {}
    source_notes = window.chord_analysis_notes()
    window.current_chord_base_weights = window.chord_base_pitch_weights(source_notes, context)
    analysis_notes = window.filtered_chord_analysis_notes(source_notes, context)
    sample_text = window.chord_sample_text(source_notes)
    scoring_options = window.chord_scoring_options()
    selection = window.timeline.selection_range()
    if selection is not None:
        start, end = selection
        required, excluded = window.chord_note_constraints()
        overlapping_notes = set(window.editor_project.note_index.overlapping(start, end))
        region_analysis_notes = [note for note in analysis_notes if note in overlapping_notes]
        analysis = analyze_chord_region(
            region_analysis_notes,
            start,
            end,
            required_pitch_classes=required,
            excluded_pitch_classes=excluded,
            scoring_options=scoring_options,
        )
        window.refresh_current_theory(source_notes, seconds)
        chord = window.display_chord(analysis.label)
        window.current_chord.setText(
            f"Selection: {chord}  (score {analysis.confidence:.0%})  "
            f"{format_time(start)} - {format_time(end)}"
        )
        window._set_chord_candidates(analysis)
        window.refresh_current_gap_suggestions(source_notes)
        window.update_harmony_context("selection", source_notes, analysis_notes, analysis)
        window.populate_note_filter_list(window.current_chord_base_weights)
        if analysis.note_weights:
            note_text = ", ".join(
                f"{window.display_weighted_note_name(name)} ({weight:.0%})"
                for name, weight in analysis.note_weights[:12]
            )
            window.set_chord_context_text(f"{sample_text}\nWeighted notes: {note_text}")
        elif analysis.active_note_names:
            note_text = ", ".join(analysis.active_note_names[:32])
            if len(analysis.active_note_names) > 32:
                note_text += f", +{len(analysis.active_note_names) - 32} more"
            window.set_chord_context_text(f"{sample_text}\nNotes in selection: {note_text}")
        else:
            window.set_chord_context_text(f"{sample_text}\nNotes in selection: -")
        return

    required, excluded = window.chord_note_constraints()
    active_index_notes = set(window.editor_project.note_index.active_at(seconds))
    point_analysis_notes = [note for note in analysis_notes if note in active_index_notes]
    analysis = analyze_chord_at(
        point_analysis_notes,
        seconds,
        required_pitch_classes=required,
        excluded_pitch_classes=excluded,
        scoring_options=scoring_options,
    )
    active_notes = sorted(point_analysis_notes, key=lambda note: (note.pitch, note.stem))
    window.refresh_current_theory(source_notes, seconds)
    chord = window.display_chord(analysis.label)
    window.current_chord.setText(f"Harmony: {chord}  (score {analysis.confidence:.0%})")
    window._set_chord_candidates(analysis)
    window.refresh_current_gap_suggestions(source_notes)
    window.update_harmony_context("playhead", source_notes, analysis_notes, analysis)
    window.populate_note_filter_list(window.current_chord_base_weights)
    if active_notes:
        unique_pitches = sorted({note.pitch for note in active_notes})
        shown_pitches = unique_pitches[:32]
        note_text = ", ".join(window.display_note_name(pitch) for pitch in shown_pitches)
        if len(unique_pitches) > len(shown_pitches):
            note_text += f", +{len(unique_pitches) - len(shown_pitches)} more"
        window.set_chord_context_text(f"{sample_text}\nNotes: {note_text}")
    else:
        window.set_chord_context_text(f"{sample_text}\nNotes: -")


def chord_context_key(window, seconds: float):
    return inspector_harmony_context_key(seconds, window.timeline.selection_range())


def chord_analysis_notes(window):
    return selected_chord_analysis_notes(
        window.editor_project,
        window.selected_chord_analysis_tracks(),
    )


def chord_sample_text(window, notes) -> str:
    if window.editor_project is None:
        return "Sample: -"
    return inspector_chord_sample_text(window.chord_analysis_track_names(), len(notes))


def selected_chord_analysis_tracks(window) -> set[str] | None:
    if not window.track_analysis_checks:
        return None
    return {
        stem_name
        for stem_name, checkbox in window.track_analysis_checks.items()
        if checkbox.isChecked()
    }


def chord_base_pitch_weights(_window, notes, context) -> dict[int, float]:
    return inspector_chord_base_pitch_weights(notes, context)


def filtered_chord_analysis_notes(window, notes, _context):
    _required, excluded_pitch_classes = window.chord_note_constraints()
    return inspector_filtered_chord_analysis_notes(notes, excluded_pitch_classes)


def chord_note_constraints(window) -> tuple[set[int], set[int]]:
    return inspector_chord_note_constraints(window.chord_note_overrides)


def populate_note_filter_list(window, weights: dict[int, float]) -> None:
    harmony_panel.populate_note_filter_list(window, weights)


def handle_chord_note_filter_changed(window, item) -> None:
    from PySide6.QtCore import Qt

    if window.updating_chord_note_filter:
        return
    pitch_class = item.data(Qt.UserRole)
    if pitch_class is None:
        return
    pitch_class = int(pitch_class)
    state = {
        Qt.Unchecked: "exclude",
        Qt.PartiallyChecked: "auto",
        Qt.Checked: "force",
    }.get(item.checkState(), "auto")
    if state == "auto":
        window.chord_note_overrides.pop(pitch_class, None)
    else:
        window.chord_note_overrides[pitch_class] = state
    window.refresh_current_harmony(window.timeline.position, force=True)


def reset_chord_note_filter(window) -> None:
    window.chord_note_overrides = {}
    window.refresh_current_harmony(window.timeline.position, force=True)
