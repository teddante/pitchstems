from __future__ import annotations

from dataclasses import dataclass

from pitchstems.editor_review_target import (
    review_ranges,
    review_ranges_brief_text,
    single_review_range,
)
from pitchstems.editor_project import analyze_chord_at, analyze_chord_regions
from pitchstems.chord_gap_analysis import analyze_chord_gap
from pitchstems.harmony_inspector import (
    chord_base_pitch_weights as inspector_chord_base_pitch_weights,
    chord_note_constraints as inspector_chord_note_constraints,
    chord_sample_text as inspector_chord_sample_text,
    filtered_chord_analysis_notes as inspector_filtered_chord_analysis_notes,
    harmony_context_key as inspector_harmony_context_key,
    selected_chord_analysis_notes,
)
from pitchstems import harmony_panel
from pitchstems.theory import analyze_theory_at, analyze_theory_region


@dataclass
class HarmonyRefreshGate:
    min_interval_seconds: float = 0.25
    last_refresh_seconds: float | None = None

    def should_refresh(self, now_seconds: float, force: bool = False) -> bool:
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
    context = chord_context_key(window, seconds)
    if context != window.chord_note_filter_context:
        window.chord_note_filter_context = context
        window.chord_note_overrides = {}
        if hasattr(window, "theory_note_overrides"):
            window.theory_note_overrides = {}
        if hasattr(window, "piano_chord_view"):
            window.piano_chord_view.set_note_constraints(window.chord_note_overrides)
        if hasattr(window, "theory_scale_view"):
            window.theory_scale_view.set_note_constraints(getattr(window, "theory_note_overrides", {}))
    source_notes = chord_analysis_notes(window)
    window.current_chord_base_weights = chord_base_pitch_weights(source_notes, context)
    analysis_notes = filtered_chord_analysis_notes(window, source_notes, context)
    sample_text = chord_sample_text(window, source_notes)
    scoring_options = window.chord_scoring_options()
    explicit_ranges = window.timeline.selection_ranges()
    selection_ranges = review_ranges(explicit_ranges, window.timeline.selected_chord)
    if selection_ranges:
        required, excluded = chord_note_constraints(window)
        region_analysis_notes = analysis_notes_overlapping_ranges(
            window.editor_project,
            analysis_notes,
            selection_ranges,
        )
        analysis = analyze_chord_regions(
            region_analysis_notes,
            selection_ranges,
            required_pitch_classes=required,
            excluded_pitch_classes=excluded,
            scoring_options=scoring_options,
        )
        window.refresh_current_theory(source_notes, seconds)
        chord = window.display_chord(analysis.label)
        range_text = review_ranges_brief_text(selection_ranges)
        label = "Selected chord" if not explicit_ranges and window.timeline.selected_chord is not None else "Selection"
        window.current_chord.setText(
            f"{label}: {chord}  (score {analysis.confidence:.0%})  "
            f"{range_text}"
        )
        harmony_panel.set_chord_candidates(window, analysis)
        window.refresh_current_gap_suggestions(source_notes)
        window.update_harmony_context("selection")
        populate_note_filter_list(window, window.current_chord_base_weights)
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
            window.set_chord_context_text(f"{sample_text}\nNotes in {label.lower()}: {note_text}")
        else:
            window.set_chord_context_text(f"{sample_text}\nNotes in {label.lower()}: -")
        return

    required, excluded = chord_note_constraints(window)
    point_analysis_notes = analysis_notes_active_at(window.editor_project, analysis_notes, seconds)
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
    harmony_panel.set_chord_candidates(window, analysis)
    window.refresh_current_gap_suggestions(source_notes)
    window.update_harmony_context("playhead")
    populate_note_filter_list(window, window.current_chord_base_weights)
    if active_notes:
        unique_pitches = sorted({note.pitch for note in active_notes})
        shown_pitches = unique_pitches[:32]
        note_text = ", ".join(window.display_note_name(pitch) for pitch in shown_pitches)
        if len(unique_pitches) > len(shown_pitches):
            note_text += f", +{len(unique_pitches) - len(shown_pitches)} more"
        window.set_chord_context_text(f"{sample_text}\nNotes: {note_text}")
    else:
        window.set_chord_context_text(f"{sample_text}\nNotes: -")


def analysis_notes_overlapping_ranges(editor_project, notes, ranges: list[tuple[float, float]]):
    overlapping_notes = set()
    for start, end in ranges:
        overlapping_notes.update(editor_project.note_index.overlapping(start, end))
    return [note for note in notes if note in overlapping_notes]


def analysis_notes_active_at(editor_project, notes, seconds: float):
    active_notes = set(editor_project.note_index.active_at(seconds))
    return [note for note in notes if note in active_notes]


def chord_context_key(window, seconds: float):
    ranges = review_ranges(window.timeline.selection_ranges(), window.timeline.selected_chord)
    return inspector_harmony_context_key(
        seconds,
        single_review_range(ranges),
        ranges,
    )


def refresh_current_theory(window, source_notes, seconds: float) -> None:
    if window.editor_project is None:
        window.set_theory_analysis(None)
        return
    selection_ranges = review_ranges(window.timeline.selection_ranges(), window.timeline.selected_chord)
    if len(selection_ranges) > 1:
        window.set_theory_analysis(None)
        return
    required, excluded = theory_note_constraints(window)
    selection = single_review_range(selection_ranges)
    if selection is not None:
        start, end = selection
        analysis = analyze_theory_region(
            source_notes,
            window.editor_project.chords,
            start,
            end,
            required_pitch_classes=required,
            excluded_pitch_classes=excluded,
        )
    else:
        analysis = analyze_theory_at(
            source_notes,
            window.editor_project.chords,
            seconds,
            required_pitch_classes=required,
            excluded_pitch_classes=excluded,
        )
    window.set_theory_analysis(analysis)


def refresh_current_gap_suggestions(window, source_notes) -> None:
    if window.editor_project is None:
        window.set_gap_analysis(None)
        return
    gap = current_chord_gap_range(window)
    if gap is None:
        window.set_gap_analysis(None)
        return
    start, end = gap
    analysis = analyze_chord_gap(
        source_notes,
        window.editor_project.chords,
        start,
        end,
        scoring_options=window.chord_scoring_options(),
    )
    window.set_gap_analysis(analysis)


def current_chord_gap_range(window) -> tuple[float, float] | None:
    if window.editor_project is None:
        return None
    selection = window.timeline.selection_range()
    if selection is not None:
        start, end = selection
        if end - start >= 0.05:
            return start, end
        return None
    return window.editor_project.chord_index.gap_at(window.timeline.position)


def chord_analysis_notes(window):
    return selected_chord_analysis_notes(
        window.editor_project,
        selected_chord_analysis_tracks(window),
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


def chord_base_pitch_weights(notes, context) -> dict[int, float]:
    return inspector_chord_base_pitch_weights(notes, context)


def filtered_chord_analysis_notes(window, notes, _context):
    _required, excluded_pitch_classes = chord_note_constraints(window)
    return inspector_filtered_chord_analysis_notes(notes, excluded_pitch_classes)


def chord_note_constraints(window) -> tuple[set[int], set[int]]:
    return inspector_chord_note_constraints(window.chord_note_overrides)


def theory_note_constraints(window) -> tuple[set[int], set[int]]:
    return inspector_chord_note_constraints(getattr(window, "theory_note_overrides", {}))


def populate_note_filter_list(window, weights: dict[int, float]) -> None:
    harmony_panel.populate_note_filter_list(window, weights)
    if hasattr(window, "piano_chord_view"):
        window.piano_chord_view.set_note_constraints(window.chord_note_overrides)


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
    if hasattr(window, "piano_chord_view"):
        window.piano_chord_view.set_note_constraints(window.chord_note_overrides)
    window.refresh_current_harmony(window.timeline.position, force=True)
