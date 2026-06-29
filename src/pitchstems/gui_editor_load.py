from __future__ import annotations

import threading
from pathlib import Path

from pitchstems.editor_loader import build_editor_load_result
from pitchstems.editor_state import editor_float
from pitchstems.evidence_display import percent_with_bar
from pitchstems.gui_editor_model import EditorSummaryModel
from pitchstems.gui_helpers import blocked_signals
from pitchstems.gui_project_flow import remember_recent_project
from pitchstems.time_format import format_time


def set_current_result(window, result, open_output: bool = True) -> None:
    window.logger.info("Setting current result: %s", result.project_dir)
    window.stop_transport()
    window.set_activity_message("Loading result...")
    token = window.editor_load_jobs.next()
    _apply_current_result_state(window, result)
    window.run_midi.setEnabled(True)
    window.export_button.setEnabled(True)
    if getattr(window, "export_action", None) is not None:
        window.export_action.setEnabled(True)
    window.separation_status.setText(f"Ready: {len(result.stems)} stems saved in {result.project_dir / 'stems'}")
    window.midi_status.setText(
        f"Ready: {len(result.midi_files)} MIDI files. Change Basic Pitch settings or MIDI stem ticks, then use Rerun MIDI only."
    )
    window.editor_summary.setText("Building editor timeline...")
    window.fit_song_button.setEnabled(False)
    window.fit_review_button.setEnabled(False)
    window.play_review_button.setEnabled(False)
    window.previous_chord_button.setEnabled(False)
    window.next_chord_button.setEnabled(False)
    window.clear_transport_players()
    remember_recent_project(window, result.project_dir)
    if open_output and window.open_when_done.isChecked():
        window.open_latest_output()
    window.start_editor_project_load(result, token)


def _apply_current_result_state(window, result) -> None:
    window.current_result = result
    window.midi_preview_jobs.next()
    window.current_stems = result.stems
    window.current_input_stem = result.normalized_audio.stem
    window.latest_output_dir = result.project_dir
    window.base_editor_project = None
    window.editor_project = None
    window.manual_chords = []
    window.removed_chord_ranges = []
    window.rendering_midi_previews.clear()


def start_editor_project_load(window, result, token: int) -> None:
    window.logger.info("Starting editor project load: %s", result.project_dir)
    window.editor_load_jobs.activity_tokens.add(token)
    window.begin_activity("Building editor project...")

    def worker() -> None:
        try:
            loaded = build_editor_load_result(result)
            if window.editor_load_jobs.closing or token != window.editor_load_jobs.token:
                return
            window.messages.put(("EDITOR_LOADED", token, loaded))
        except Exception as exc:
            window.logger.exception("Editor project load failed")
            if window.editor_load_jobs.closing or token != window.editor_load_jobs.token:
                return
            window.messages.put(("EDITOR_LOAD_FAILED", token, result.project_dir, f"{exc}"))

    window.editor_load_jobs.worker = threading.Thread(
        target=worker,
        name="PitchStemsEditorLoad",
        daemon=True,
    )
    window.editor_load_jobs.worker.start()


def finish_editor_project_load(window, token: int, loaded) -> None:
    if token != window.editor_load_jobs.token or window.current_result is None:
        window.logger.info("Ignored stale editor load for %s", loaded.pipeline_result.project_dir)
        window.finish_editor_load_activity(token, "Ready")
        return
    if window.current_result.project_dir != loaded.pipeline_result.project_dir:
        window.logger.info("Ignored editor load for inactive project: %s", loaded.pipeline_result.project_dir)
        window.finish_editor_load_activity(token, "Ready")
        return

    editor_state = _apply_loaded_editor_result(window, loaded)
    window.logger.info(
        "Editor model built: tracks=%d notes=%d chords=%d",
        len(window.editor_project.tracks),
        len(window.editor_project.notes),
        len(window.editor_project.chords),
    )
    project = window.editor_project
    track_visibility = editor_state.get("track_visibility", {})
    notation_spelling = editor_state.get("notation_spelling", "auto")
    notation_index = window.notation_spelling.findData(notation_spelling)
    if notation_index >= 0:
        with blocked_signals(window.notation_spelling):
            window.notation_spelling.setCurrentIndex(notation_index)
    playhead_seconds = editor_float(editor_state.get("playhead_seconds"), 0.0, low=0.0)
    summary = EditorSummaryModel(
        track_count=len(project.tracks),
        note_count=len(project.notes),
        duration_seconds=project.duration,
    )
    window.editor_summary.setText(summary.summary)
    maximum = max(0, int(project.duration * 1000))
    window.fit_song_button.setEnabled(summary.fit_song_enabled and maximum > 0)
    window.fit_review_button.setEnabled(summary.fit_song_enabled and maximum > 0)
    window.play_review_button.setEnabled(summary.fit_song_enabled and maximum > 0)
    window.previous_chord_button.setEnabled(bool(project.chords))
    window.next_chord_button.setEnabled(bool(project.chords))
    window.editor_position.setText(format_time(playhead_seconds))
    refresh_editor_lists(window, track_visibility)
    window.refresh_playback_controls(editor_state)
    window.clear_transport_players()
    window.logger.info("Drawing editor timeline")
    window.set_activity_message("Drawing editor timeline...")
    window.timeline.set_project(project, redraw=False)
    window.timeline.set_manual_chords(window.manual_chords, redraw=False)
    window.timeline.set_visible_tracks(
        {track.name for track in project.tracks if track_visibility.get(track.name, True)},
        redraw=False,
    )
    window.timeline.redraw()
    window.set_editor_position_seconds(playhead_seconds)
    window.main_tabs.setCurrentIndex(1)
    window.logger.info("Editor project loaded")
    window.finish_editor_load_activity(token, "Editor project loaded")


def _apply_loaded_editor_result(window, loaded) -> dict:
    window.base_editor_project = loaded.base_project
    window.editor_project = loaded.editor_project
    window.manual_chords = loaded.manual_chords
    window.removed_chord_ranges = loaded.removed_chord_ranges
    return loaded.editor_state


def finish_editor_project_load_failed(window, token: int, project_dir: Path, error: str) -> None:
    if token != window.editor_load_jobs.token:
        window.logger.info("Ignored stale editor load failure for %s: %s", project_dir, error)
        window.finish_editor_load_activity(token, "Ready")
        return
    window.logger.error("Could not open project editor for %s: %s", project_dir, error)
    window.append_log(f"Could not open project editor: {error}")
    window.append_log(f"Log file: {window.log_path}")
    window.editor_summary.setText("Could not build editor timeline.")
    window.timeline.set_project(None)
    window.finish_editor_load_activity(token, "Could not open project editor")


def finish_editor_load_activity(window, token: int, message: str) -> None:
    if token not in window.editor_load_jobs.activity_tokens:
        return
    window.editor_load_jobs.activity_tokens.discard(token)
    window.end_activity(message)


def refresh_editor_lists(window, track_visibility: dict[str, bool] | None = None) -> None:
    track_visibility = track_visibility or {}
    window.editor_track_visibility = track_visibility
    window.track_note_counts = {}
    window.chord_list.clear()
    window.refresh_chord_keyboard()
    if window.editor_project is None:
        return
    for note in window.editor_project.notes:
        window.track_note_counts[note.stem] = window.track_note_counts.get(note.stem, 0) + 1
    refresh_detected_chord_list(window)


def refresh_detected_chord_list(window) -> None:
    window.chord_list.clear()
    if window.editor_project is None:
        return
    for chord in window.editor_project.chords[:200]:
        window.chord_list.addItem(
            f"{format_time(chord.start)}  {window.display_chord(chord.label)}  "
            f"{chord_source_label(window, chord)}  ({percent_with_bar(chord.confidence)})"
        )
    if len(window.editor_project.chords) > 200:
        window.chord_list.addItem(f"... {len(window.editor_project.chords) - 200} more")
    window.refresh_chord_actions()
    window.refresh_chord_keyboard()


def chord_source_label(window, chord) -> str:
    return "Edited" if chord in window.manual_chords else "Auto"
