from __future__ import annotations

from pitchstems.chord_regions import merge_chord_ranges
from pitchstems.editor_chord_assignment import chord_assignment_ranges, chord_assignment_target_text
from pitchstems.editor_loader import apply_chord_edits
from pitchstems.editor_project import ChordRegion
from pitchstems.editor_state import build_editor_state_snapshot, save_editor_state_snapshot
from pitchstems.gui_helpers import blocked_signals
from pitchstems.time_format import format_time


def apply_manual_chords(window) -> None:
    if window.editor_project is None or (not window.manual_chords and not window.removed_chord_ranges):
        return
    window.editor_project = apply_chord_edits(
        window.editor_project,
        window.manual_chords,
        window.removed_chord_ranges,
    )


def refresh_editor_project_from_chord_edits(
    window,
    selected_chord: ChordRegion | None = None,
) -> None:
    if window.current_result is None or window.base_editor_project is None:
        return
    position = window.timeline.position
    selection_start = window.timeline.selection_start
    selection_end = window.timeline.selection_end
    window.editor_project = window.base_editor_project
    window.apply_manual_chords()
    window.timeline.project = window.editor_project
    window.timeline._index_project()
    window.timeline.visible_tracks = {
        stem_name.lower()
        for stem_name, checkbox in window.track_visibility_checks.items()
        if checkbox.isChecked()
    }
    window.timeline.position = position
    window.timeline.selection_start = selection_start
    window.timeline.selection_end = selection_end
    window.timeline.selected_chord = selected_chord
    window.timeline.set_manual_chords(window.manual_chords)
    window.refresh_detected_chord_list()
    window.refresh_current_harmony(window.timeline.position, force=True)
    window.save_editor_state()


def assign_selected_chord_to_selection(window) -> None:
    from PySide6.QtCore import Qt

    if not _has_loaded_editor_project(window):
        return
    explicit_ranges = window.timeline.selection_ranges()
    selection_ranges = chord_assignment_ranges(
        explicit_ranges,
        window.timeline.selected_chord,
    )
    item = window.chord_list.currentItem()
    if not selection_ranges or item is None:
        return
    label = item.data(Qt.UserRole)
    confidence = float(item.data(Qt.UserRole + 1) or 1.0)
    if not label:
        return
    selected_chord = None
    for start, end in selection_ranges:
        selected_chord = ChordRegion(start=start, end=end, label=label, confidence=confidence)
        window.insert_manual_chord(selected_chord)
    window.refresh_editor_project_from_chord_edits(selected_chord)
    target_chord = None if explicit_ranges else window.timeline.selected_chord
    range_text = chord_assignment_target_text(selection_ranges, target_chord)
    window.statusBar().showMessage(
        f"Assigned {window.display_chord(label)} to {range_text}.",
        5000,
    )


def delete_selected_chord(window) -> None:
    if not _has_loaded_editor_project(window):
        return
    if window.timeline.selection_ranges():
        window.statusBar().showMessage("Clear the timeline range before deleting a chord.", 4000)
        return
    chord = window.timeline.selected_chord
    if chord is None:
        window.statusBar().showMessage("Select a chord block before deleting it.", 4000)
        return
    delete_timeline_chord(window, chord)


def insert_manual_chord(window, chord: ChordRegion) -> None:
    window.manual_chords = [
        existing
        for existing in window.manual_chords
        if existing.end <= chord.start or existing.start >= chord.end
    ]
    window.removed_chord_ranges = merge_chord_ranges(
        [*window.removed_chord_ranges, (chord.start, chord.end)]
    )
    window.manual_chords.append(chord)
    window.manual_chords.sort(key=lambda item: (item.start, item.end, item.label))


def edit_timeline_chord(window, original: ChordRegion, edited: ChordRegion) -> None:
    window.removed_chord_ranges = merge_chord_ranges(
        [*window.removed_chord_ranges, (original.start, original.end), (edited.start, edited.end)]
    )
    window.manual_chords = [chord for chord in window.manual_chords if chord != original]
    window.insert_manual_chord(edited)
    window.refresh_editor_project_from_chord_edits(edited)
    window.statusBar().showMessage(
        f"Moved {window.display_chord(edited.label)} to {format_time(edited.start)} - {format_time(edited.end)}.",
        5000,
    )


def delete_timeline_chord(window, chord: ChordRegion) -> None:
    window.removed_chord_ranges = merge_chord_ranges(
        [*window.removed_chord_ranges, (chord.start, chord.end)]
    )
    window.manual_chords = [manual for manual in window.manual_chords if manual != chord]
    window.refresh_editor_project_from_chord_edits(None)
    window.statusBar().showMessage(f"Deleted {window.display_chord(chord.label)}.", 4000)


def show_timeline_chord_status(window, chord: ChordRegion | None) -> None:
    window.refresh_current_harmony(window.timeline.position, force=True)
    window.refresh_chord_actions()
    if chord is None:
        window.refresh_chord_keyboard()
        return
    window.refresh_chord_keyboard()
    window.statusBar().showMessage(
        f"Selected {window.display_chord(chord.label)}: Play loops this chord; drag middle to move, drag edges to resize, Delete removes it.",
        6000,
    )


def refresh_visible_tracks(window) -> None:
    visible = {
        stem_name
        for stem_name, checkbox in window.track_visibility_checks.items()
        if checkbox.isChecked()
    }
    window.timeline.set_visible_tracks(visible)
    window.refresh_current_harmony(window.timeline.position, force=True)
    window.save_editor_state()


def show_all_timeline_tracks(window) -> None:
    for checkbox in window.track_visibility_checks.values():
        with blocked_signals(checkbox):
            checkbox.setChecked(True)
    window.refresh_visible_tracks()


def save_editor_state(window) -> bool:
    if not _has_loaded_editor_project(window):
        return False
    if window.editor_save_timer.isActive():
        window.editor_save_timer.stop()
    snapshot = build_editor_state_snapshot(
        track_visibility_checks=window.track_visibility_checks,
        track_analysis_checks=window.track_analysis_checks,
        track_audio_checks=window.track_audio_checks,
        track_audio_sliders=window.track_audio_sliders,
        track_midi_checks=window.track_midi_checks,
        track_midi_sliders=window.track_midi_sliders,
        notation_spelling=window.selected_notation_preference(),
        playhead_seconds=window.timeline.position,
        manual_chords=window.manual_chords,
        removed_chord_ranges=window.removed_chord_ranges,
    )
    try:
        save_editor_state_snapshot(window.current_result, snapshot)
    except Exception as exc:
        window.logger.exception("Could not save editor state")
        window.statusBar().showMessage(f"Could not save project state: {exc}", 6000)
        return False
    return True


def request_editor_state_save(window, delay_ms: int = 750) -> None:
    if not _has_loaded_editor_project(window):
        return
    window.editor_save_timer.start(delay_ms)


def _has_loaded_editor_project(window) -> bool:
    return window.current_result is not None and window.editor_project is not None
