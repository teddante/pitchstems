from __future__ import annotations


def prepare_transport_players(window, result) -> None:
    window.set_activity_message("Preparing audio players...")
    window.pause_transport()
    window.transport.prepare_players(result)
    if window.editor_project is not None:
        window.transport.prepare_midi_synth(window.editor_project.notes, window.editor_project.duration)
    window.refresh_playback_mix()


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


def finish_transport_at_end(window) -> None:
    window.play_button.setText("Play")
    window.stop_button.setEnabled(False)
    window.transport_timer.stop()
    if window.editor_project is not None:
        window.set_editor_position_seconds(0.0, save=False, seek_players=False)
    window.save_editor_state()


def update_transport_position(window) -> None:
    master = window.transport_master_player()
    if master is None:
        return
    seconds = master.position() / 1000
    window.resync_transport_players(master)
    selection = window.loop_playback_range()
    if selection is not None:
        start, end = selection
        if seconds >= end:
            window.seek_audio_players(start)
            window.set_editor_position_seconds(start, save=False, seek_players=False)
            return
    window.set_editor_position_seconds(seconds, save=False, seek_players=False)
