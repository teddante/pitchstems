from __future__ import annotations

import threading
from pathlib import Path

from pitchstems.gui_transport import find_existing_midi_previews, loop_playback_start
from pitchstems.midi_preview import render_midi_preview


def prepare_transport_players(window, result) -> None:
    window.set_activity_message("Preparing audio players...")
    window.pause_transport()
    window.transport.prepare_players(result)
    window.attach_midi_preview_players(dict(window.transport.midi_preview_paths), finish_activity=False)
    requested_midi = {
        stem_name
        for stem_name, checkbox in window.track_midi_checks.items()
        if checkbox.isChecked() and stem_name not in window.transport.midi_preview_paths
    }
    if requested_midi:
        window.start_midi_preview_render(result, requested_midi)
    window.refresh_playback_mix()


def clear_transport_players(window) -> None:
    window.transport.clear_players()


def transport_players(window):
    return window.transport.players()


def start_midi_preview_render(window, result, requested_stems: set[str] | None = None) -> None:
    if window.midi_preview_jobs.closing:
        return
    if window.editor_project is None or not window.editor_project.notes:
        return
    requested_keys = {stem.lower() for stem in (requested_stems or set())}
    missing = [
        track.name
        for track in window.editor_project.tracks
        if (not requested_keys or track.name.lower() in requested_keys)
        if track.name not in window.transport.midi_preview_paths
        and any(note.stem.lower() == track.name.lower() for note in window.editor_project.notes)
        and not window._midi_preview_worker_running(result.project_dir, track.name)
    ]
    if not missing:
        return
    project = window.editor_project
    preview_dir = result.project_dir / "editor" / "midi-preview"
    token = window.midi_preview_jobs.token
    window.rendering_midi_previews.update(missing)
    window.refresh_timeline_track_summaries()
    window.append_log(f"Rendering MIDI preview audio for {', '.join(missing)} in the background...")
    window.begin_activity("Rendering MIDI preview audio...")

    def worker() -> None:
        previews: dict[str, Path] = {}
        try:
            for stem_name in missing:
                preview = render_midi_preview(
                    stem_name,
                    project.notes,
                    preview_dir,
                    project.duration,
                )
                if preview:
                    previews[stem_name] = preview
            if window.midi_preview_jobs.closing or token != window.midi_preview_jobs.token:
                return
            window.messages.put(("MIDI_PREVIEWS", token, result.project_dir, set(missing), previews))
        except Exception as exc:
            window.logger.exception("MIDI preview render failed")
            if window.midi_preview_jobs.closing or token != window.midi_preview_jobs.token:
                return
            window.messages.put(
                (
                    "MIDI_PREVIEW_FAILED",
                    token,
                    result.project_dir,
                    set(missing),
                    f"Could not render MIDI previews: {exc}",
                )
            )

    worker_thread = threading.Thread(target=worker, daemon=True)
    for stem_name in missing:
        window.midi_preview_jobs.workers[(result.project_dir, stem_name.lower())] = (token, worker_thread)
    worker_thread.start()


def midi_preview_worker_running(window, project_dir: Path, stem_name: str) -> bool:
    key = (project_dir, stem_name.lower())
    entry = window.midi_preview_jobs.workers.get(key)
    if entry is None:
        return False
    token, worker = entry
    if token != window.midi_preview_jobs.token or not worker.is_alive():
        window.midi_preview_jobs.workers.pop(key, None)
        return False
    return True


def clear_midi_preview_worker(window, project_dir: Path, stem_name: str, token: int) -> None:
    key = (project_dir, stem_name.lower())
    entry = window.midi_preview_jobs.workers.get(key)
    if entry is not None and entry[0] == token:
        window.midi_preview_jobs.workers.pop(key, None)


def attach_midi_preview_players(window, previews: dict[str, Path], finish_activity: bool = True) -> None:
    if not previews:
        window.refresh_timeline_track_summaries()
        if finish_activity:
            window.end_activity("No MIDI preview audio rendered")
        return
    for stem_name in previews:
        window.rendering_midi_previews.discard(stem_name)
    window.transport.attach_midi_preview_players(previews, window.timeline.position)
    window.refresh_playback_mix()
    window.refresh_timeline_track_summaries()
    if finish_activity:
        window.append_log(f"MIDI preview audio ready: {len(previews)} tracks.")
        window.end_activity("MIDI preview audio ready")


def refresh_playback_mix(window) -> None:
    window.transport.refresh_mix()
    window.apply_midi_transport_state()


def midi_track_enabled(window, stem_name: str) -> bool:
    return window.transport.midi_track_enabled(stem_name)


def apply_midi_transport_state(window) -> None:
    window.transport.apply_midi_transport_state(window.timeline.position)


def toggle_playback(window) -> None:
    if window.transport.is_playing:
        window.pause_transport()
    else:
        window.play_transport()


def play_transport(window) -> None:
    from PySide6.QtCore import QTimer

    if window.editor_project is None or window.current_result is None:
        window.append_log("Open or run a project before playback.")
        return
    if not window.transport.track_players:
        window.append_log("Preparing playback...")
        window.begin_activity("Preparing playback...")
        window.prepare_transport_players(window.current_result)
        window.end_activity("Playback ready")
    window.refresh_playback_mix()
    start_position = window.loop_playback_start_seconds()
    if start_position != window.timeline.position:
        window.set_editor_position_seconds(start_position, save=False, seek_players=False)
    window.transport.play(start_position)
    window.play_button.setText("Pause")
    window.stop_button.setEnabled(True)
    window.transport_timer.start(80)
    QTimer.singleShot(250, window.resync_transport_players)


def pause_transport(window) -> None:
    if not window.transport.pause():
        return
    window.play_button.setText("Play")
    window.transport_timer.stop()
    window.save_editor_state()


def stop_transport(window) -> None:
    window.transport.stop()
    window.play_button.setText("Play")
    window.stop_button.setEnabled(False)
    window.transport_timer.stop()
    if window.editor_project is not None:
        window.set_editor_position_seconds(0.0, seek_players=False)


def seek_audio_players(window, seconds: float) -> None:
    window.transport.seek(seconds)


def update_transport_position(window) -> None:
    master = window.transport_master_player()
    if master is None:
        return
    seconds = master.position() / 1000
    window.resync_transport_players(master)
    selection = window.timeline.selection_range()
    if selection is not None:
        start, end = selection
        if seconds >= end:
            window.seek_audio_players(start)
            window.set_editor_position_seconds(start, save=False, seek_players=False)
            return
    window.set_editor_position_seconds(seconds, save=False, seek_players=False)


def transport_master_player(window):
    return window.transport.master_player()


def resync_transport_players(window, master=None) -> None:
    window.transport.resync(master)


def loop_playback_start_seconds(window) -> float:
    return loop_playback_start(window.timeline.position, window.timeline.selection_range())


def existing_midi_previews(result) -> dict[str, Path]:
    return find_existing_midi_previews(result)
