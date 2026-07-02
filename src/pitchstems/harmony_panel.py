from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem

from pitchstems.editor_chord_assignment import chord_assignment_ranges
from pitchstems.editor_project import ChordRegion
from pitchstems.evidence_display import percent_with_bar
from pitchstems.chord_explanation import partial_harmony_note_order
from pitchstems.time_format import format_time


def set_gap_analysis(window, analysis) -> None:
    window.current_chord_gap_analysis = analysis
    window.gap_suggestion_list.clear()
    if analysis is None or not analysis.suggestions:
        window.gap_suggestion_list.addItem(
            getattr(window, "current_gap_empty_message", "No chord-track gap selected or under the playhead.")
        )
        refresh_gap_suggestion_actions(window)
        return
    window.gap_suggestion_list.addItem(f"Gap {format_time(analysis.start)} - {format_time(analysis.end)}")
    for index, suggestion in enumerate(analysis.suggestions[:8]):
        item = QListWidgetItem(
            f"{window.display_chord(suggestion.label)}  {suggestion.score:.0%}\n"
            f"{suggestion.action.replace('_', ' ')} | local {suggestion.local_evidence:.0%}, "
            f"theory {suggestion.theory_fit:.0%}, movement {suggestion.pitch_class_movement:.0%}"
        )
        item.setData(Qt.UserRole, index)
        item.setToolTip("\n".join(suggestion.explanation))
        window.gap_suggestion_list.addItem(item)
    window.gap_suggestion_list.setCurrentRow(1)
    refresh_gap_suggestion_actions(window)


def refresh_gap_suggestion_actions(window) -> None:
    item = window.gap_suggestion_list.currentItem()
    has_suggestion = bool(item and item.data(Qt.UserRole) is not None)
    window.use_gap_suggestion_button.setEnabled(has_suggestion)
    window.inspect_gap_suggestion_button.setEnabled(
        window.current_chord_gap_analysis is not None
        and bool(window.current_chord_gap_analysis.suggestions)
    )


def populate_note_filter_list(window, weights: dict[int, float]) -> None:
    window.updating_chord_note_filter = True
    try:
        window.note_filter_list.clear()
        detected = sorted(weights, key=lambda pitch_class: (-weights[pitch_class], pitch_class))
        missing = [pitch_class for pitch_class in range(12) if pitch_class not in weights]
        for pitch_class in [*detected, *missing]:
            state = window.chord_note_overrides.get(pitch_class, "auto")
            detail = f"{weights[pitch_class]:.0%}" if pitch_class in weights else "not detected"
            if state == "exclude":
                detail = f"{detail}; hard excluded"
            elif state == "force":
                detail = "forced in"
            label = {"exclude": "Exclude", "auto": "Auto", "force": "Force"}[state]
            item = QListWidgetItem(f"{label} {window.display_pitch_class_name(pitch_class)}  -  {detail}")
            item.setData(Qt.UserRole, pitch_class)
            tristate_flag = getattr(Qt, "ItemIsUserTristate", Qt.ItemIsUserCheckable)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | tristate_flag)
            check_state = {
                "exclude": Qt.Unchecked,
                "auto": Qt.PartiallyChecked,
                "force": Qt.Checked,
            }[state]
            item.setCheckState(check_state)
            item.setToolTip(
                "Unchecked: Exclude any chord name containing this note.\n"
                "Mixed: Auto, use detector evidence naturally.\n"
                "Checked: Force chord names to contain this note."
            )
            window.note_filter_list.addItem(item)
    finally:
        window.updating_chord_note_filter = False


def set_chord_candidates(window, analysis) -> None:
    if analysis.candidates:
        window.chord_list.clear()
        for label, confidence in analysis.candidates:
            display_label = window.display_chord(label)
            note_names = window.display_chord_tones(label)
            notes = candidate_notes_text(window, analysis, label)
            aliases = analysis.candidate_aliases.get(label, [])
            alias_text = ""
            if aliases:
                shown_aliases = ", ".join(window.display_chord(alias) for alias in aliases[:4])
                if len(aliases) > 4:
                    shown_aliases += f", +{len(aliases) - 4} more"
                alias_text = f"\naka: {shown_aliases}"
            item = QListWidgetItem(f"{display_label}  {percent_with_bar(confidence)}\n{notes}{alias_text}")
            item.setData(Qt.UserRole, label)
            item.setData(Qt.UserRole + 1, confidence)
            item.setData(Qt.UserRole + 2, note_names)
            item.setToolTip(
                f"{display_label}\n"
                f"Official chord tones: {notes}\n"
                f"Alternate names: {', '.join(window.display_chord(alias) for alias in aliases) if aliases else '-'}\n"
                f"Detector ranking score: {confidence:.0%}\n\n"
                + "\n".join(analysis.candidate_explanations.get(label, []))
            )
            window.chord_list.addItem(item)
    else:
        window.chord_list.clear()
        window.chord_list.addItem("No full chord candidates here.")
        for label, confidence in analysis.partial_candidates:
            display_label = window.display_chord(label)
            note_names = window.display_chord_tones(label)
            notes = partial_candidate_notes_text(window, analysis, label)
            aliases = analysis.partial_candidate_aliases.get(label, [])
            alias_text = ""
            if aliases:
                alias_text = f"\naka: {', '.join(window.display_chord(alias) for alias in aliases[:4])}"
            item = QListWidgetItem(f"{display_label}  {percent_with_bar(confidence)}\n{notes}{alias_text}")
            item.setData(Qt.UserRole, label)
            item.setData(Qt.UserRole + 1, confidence)
            item.setData(Qt.UserRole + 2, note_names)
            item.setToolTip(
                f"{display_label}\n"
                f"Observed shell tones: {notes}\n"
                "Partial/shell candidate, not a full chord detection.\n\n"
                + "\n".join(analysis.partial_candidate_explanations.get(label, []))
            )
            window.chord_list.addItem(item)
        for hint in analysis.partial_hints:
            item = QListWidgetItem(partial_hint_text(window, analysis, hint))
            item.setToolTip("Partial harmony hint. This is not a confirmed chord candidate.")
            window.chord_list.addItem(item)
    select_first_chord_candidate(window)
    refresh_chord_actions(window)


def select_first_chord_candidate(window) -> None:
    for row in range(window.chord_list.count()):
        item = window.chord_list.item(row)
        if item.data(Qt.UserRole):
            window.chord_list.setCurrentItem(item)
            return
    refresh_chord_keyboard(window)


def refresh_chord_keyboard(window) -> None:
    track_chord = active_chord_track_region(window)
    if track_chord is not None:
        note_names = window.display_chord_tones(track_chord.label)
        note_roles = window.preview_voicing_note_roles(track_chord.label) if hasattr(window, "preview_voicing_note_roles") else {}
        window.piano_chord_view.set_chord(
            window.display_chord(track_chord.label),
            note_names,
            "Chord track",
            note_roles,
        )
        if hasattr(window, "chord_fretboard_view"):
            window.chord_fretboard_view.set_chord(
                window.display_chord(track_chord.label),
                note_names,
                "Chord track",
                note_roles,
            )
        if hasattr(window.piano_chord_view, "set_note_constraints"):
            window.piano_chord_view.set_note_constraints(getattr(window, "chord_note_overrides", {}))
        if hasattr(window, "chord_fretboard_view"):
            window.chord_fretboard_view.set_note_constraints(getattr(window, "chord_note_overrides", {}))
        if hasattr(window, "set_chord_note_map_colours"):
            window.set_chord_note_map_colours(track_chord.label, note_names)
        return
    item = window.chord_list.currentItem()
    if item is None:
        window.piano_chord_view.set_chord(None, [])
        if hasattr(window, "chord_fretboard_view"):
            window.chord_fretboard_view.set_chord(None, [])
        if hasattr(window.piano_chord_view, "set_note_constraints"):
            window.piano_chord_view.set_note_constraints(getattr(window, "chord_note_overrides", {}))
        if hasattr(window, "chord_fretboard_view"):
            window.chord_fretboard_view.set_note_constraints(getattr(window, "chord_note_overrides", {}))
        if hasattr(window, "set_chord_note_map_colours"):
            window.set_chord_note_map_colours(None, [])
        return
    label = item.data(Qt.UserRole)
    if not label:
        window.piano_chord_view.set_chord(None, [])
        if hasattr(window, "chord_fretboard_view"):
            window.chord_fretboard_view.set_chord(None, [])
        if hasattr(window.piano_chord_view, "set_note_constraints"):
            window.piano_chord_view.set_note_constraints(getattr(window, "chord_note_overrides", {}))
        if hasattr(window, "chord_fretboard_view"):
            window.chord_fretboard_view.set_note_constraints(getattr(window, "chord_note_overrides", {}))
        if hasattr(window, "set_chord_note_map_colours"):
            window.set_chord_note_map_colours(None, [])
        return
    note_names = item.data(Qt.UserRole + 2) or []
    source_label = window.preview_voicing_source_label() if hasattr(window, "preview_voicing_source_label") else "Inspector"
    note_roles = window.preview_voicing_note_roles(label) if hasattr(window, "preview_voicing_note_roles") else {}
    window.piano_chord_view.set_chord(window.display_chord(label), note_names, source_label, note_roles)
    if hasattr(window, "chord_fretboard_view"):
        window.chord_fretboard_view.set_chord(window.display_chord(label), note_names, source_label, note_roles)
    if hasattr(window.piano_chord_view, "set_note_constraints"):
        window.piano_chord_view.set_note_constraints(getattr(window, "chord_note_overrides", {}))
    if hasattr(window, "chord_fretboard_view"):
        window.chord_fretboard_view.set_note_constraints(getattr(window, "chord_note_overrides", {}))
    if hasattr(window, "set_chord_note_map_colours"):
        window.set_chord_note_map_colours(label, note_names)


def active_chord_track_region(window) -> ChordRegion | None:
    if window.timeline.selected_chord is not None:
        return window.timeline.selected_chord
    if window.editor_project is None:
        return None
    position = window.timeline.position
    for chord in reversed(window.editor_project.chords):
        if chord.start <= position < chord.end:
            return chord
    return None


def candidate_notes_text(window, analysis, label: str) -> str:
    return _candidate_notes_text(window, label, analysis.candidate_notes)


def partial_candidate_notes_text(window, analysis, label: str) -> str:
    return _candidate_notes_text(window, label, analysis.partial_candidate_notes)


def partial_hint_text(window, analysis, hint: str) -> str:
    if not hint.startswith("Detected note set:"):
        return hint
    ordered = partial_harmony_note_order(set(analysis.pitch_classes), analysis.bass)
    if not ordered:
        return hint
    notes = " - ".join(window.display_pitch_class_name(pitch_class) for pitch_class in ordered)
    return f"Detected note set: {notes}."


def _candidate_notes_text(window, label: str, fallback_notes: dict[str, list[str]]) -> str:
    notes = window.display_chord_tones(label) if label else fallback_notes.get(label, [])
    if not notes:
        return "-"
    text = " - ".join(notes)
    bass_name = window.display_chord_bass(label)
    if bass_name is not None:
        text += f"  bass {bass_name}"
    return text


def refresh_chord_actions(window) -> None:
    item = window.chord_list.currentItem()
    has_candidate = bool(item and item.data(Qt.UserRole))
    explicit_ranges = window.timeline.selection_ranges()
    selected_chord = window.timeline.selected_chord
    target_ranges = chord_assignment_ranges(explicit_ranges, selected_chord)
    selected_chord_target = not explicit_ranges and selected_chord is not None
    window.preview_chord_button.setEnabled(has_candidate)
    window.use_chord_button.setEnabled(has_candidate and bool(target_ranges))
    window.delete_chord_button.setEnabled(selected_chord_target)
    if selected_chord_target:
        window.use_chord_button.setText("Use for Chord")
        window.use_chord_button.setToolTip("Replace the selected chord block with this detected harmony.")
        window.delete_chord_button.setToolTip("Remove the selected chord block from the timeline.")
    else:
        window.use_chord_button.setText("Use for Selection")
        window.use_chord_button.setToolTip("Apply this detected harmony to the selected timeline range.")
        window.delete_chord_button.setToolTip("Select a chord block to remove it.")
