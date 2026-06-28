from __future__ import annotations

from pathlib import Path

from pitchstems.app_logging import logs_dir
from pitchstems.file_opening import open_folder
from pitchstems.gui_editor_model import EMPTY_EDITOR_SUMMARY
from pitchstems.gui_helpers import blocked_signals, clear_layout
from pitchstems.input_validation import validate_audio_input
from pitchstems.project_store import PROJECT_FILENAME, load_pipeline_result
from pitchstems.recent_projects import (
    normalize_recent_project_paths,
    recent_project_label as format_recent_project_label,
    remember_recent_project as remember_project_path,
    remove_recent_project as remove_project_path,
)
from pitchstems.time_format import format_time


def refresh_recent_projects_menu(window) -> None:
    from PySide6.QtGui import QAction

    if window.recent_projects_menu is None:
        return
    window.recent_projects_menu.clear()
    recent = recent_project_paths(window)
    if not recent:
        action = QAction("No recent projects", window)
        action.setEnabled(False)
        window.recent_projects_menu.addAction(action)
        return
    for index, path in enumerate(recent[:10], 1):
        action = QAction(f"&{index} {recent_project_label(path)}", window)
        action.setToolTip(str(path))
        action.triggered.connect(
            lambda _checked=False, project_path=path: open_recent_project(window, project_path)
        )
        window.recent_projects_menu.addAction(action)
    window.recent_projects_menu.addSeparator()
    window._add_action(
        window.recent_projects_menu,
        "Clear Recent Projects",
        None,
        lambda: clear_recent_projects(window),
    )


def recent_project_paths(window) -> list[Path]:
    return normalize_recent_project_paths(window.settings.value("recent_projects", []))


def recent_project_label(manifest_path: Path) -> str:
    return format_recent_project_label(manifest_path)


def remember_recent_project(window, project_dir: Path) -> None:
    recent = remember_project_path(recent_project_paths(window), project_dir)
    window.settings.setValue("recent_projects", [str(path) for path in recent])
    refresh_recent_projects_menu(window)


def remove_recent_project(window, manifest_path: Path) -> None:
    recent = remove_project_path(recent_project_paths(window), manifest_path)
    window.settings.setValue("recent_projects", [str(path) for path in recent])
    refresh_recent_projects_menu(window)


def clear_recent_projects(window) -> None:
    window.settings.setValue("recent_projects", [])
    refresh_recent_projects_menu(window)
    window.statusBar().showMessage("Recent projects cleared.", 3000)


def open_recent_project(window, manifest_path: Path) -> None:
    if not manifest_path.exists():
        remove_recent_project(window, manifest_path)
        window.append_log(f"Recent project no longer exists: {manifest_path}")
        window.statusBar().showMessage("Recent project was removed because it no longer exists.", 5000)
        return
    window.open_project_manifest(manifest_path)


def pick_audio(window) -> None:
    from PySide6.QtWidgets import QFileDialog

    filename, _selected_filter = QFileDialog.getOpenFileName(
        window,
        "Open audio",
        str(Path.home()),
        "Audio files (*.wav *.mp3 *.flac *.m4a *.aac *.ogg);;All files (*.*)",
    )
    if filename:
        window.set_audio_path(Path(filename))


def set_audio_path(window, path: Path) -> None:
    error = validate_audio_input(path)
    if error:
        window.drop_zone.reset_prompt()
        if hasattr(window, "import_clip_picker"):
            window.import_clip_picker.reset_audio()
        window.append_log(error)
        window.statusBar().showMessage(error, 5000)
        return
    window.drop_zone.set_audio_file(path)
    window.reset_stage_state(path)


def save_project_now(window) -> None:
    if window.current_result is None:
        window.append_log("No project is open yet.")
        return
    if window.save_editor_state():
        window.append_log(f"Saved project: {window.current_result.project_dir / PROJECT_FILENAME}")


def pick_output_dir(window) -> None:
    from PySide6.QtWidgets import QFileDialog

    directory = QFileDialog.getExistingDirectory(window, "Choose output directory")
    if directory:
        window.output_dir.setText(directory)


def pick_project(window) -> None:
    from PySide6.QtWidgets import QFileDialog

    filename, _selected_filter = QFileDialog.getOpenFileName(
        window,
        "Open PitchStems project",
        str(Path(window.output_dir.text())),
        f"PitchStems Project ({PROJECT_FILENAME});;JSON files (*.json)",
    )
    if filename:
        window.open_project_manifest(Path(filename))


def open_project_manifest(window, manifest_path: Path) -> None:
    window.invalidate_worker_token()
    window.begin_activity("Opening project...")
    try:
        window.logger.info("Opening project manifest: %s", manifest_path)
        result = load_pipeline_result(manifest_path)
    except Exception as exc:
        window.logger.exception("Could not open project manifest")
        window.append_log(f"Could not open project: {exc}")
        window.end_activity("Could not open project")
        remove_recent_project(window, manifest_path)
        return
    window.output_dir.setText(str(result.project_dir.parent))
    window.drop_zone.set_project_file(result.project_dir, result.source_audio)
    if hasattr(window, "import_clip_picker"):
        window.import_clip_picker.reset_audio()
    try:
        window.logger.info("Building editor for project: %s", result.project_dir)
        window.set_current_result(result, open_output=False)
    except Exception as exc:
        window.logger.exception("Could not open project editor")
        window.append_log(f"Could not open project editor: {exc}")
        window.append_log(f"Log file: {window.log_path}")
        window.reset_stage_state()
        window.end_activity("Could not open project editor")
        return
    window.append_log(f"Opened project: {result.project_dir}")
    window.end_activity("Project loaded")


def reset_stage_state(window, path: Path | None = None) -> None:
    if hasattr(window, "stop_import_clip_preview"):
        window.stop_import_clip_preview()
    if hasattr(window, "import_clip_picker"):
        if path is None:
            window.import_clip_picker.reset_audio()
        else:
            window.import_clip_picker.set_audio_file(path, log=window.append_log)
    window.stop_transport()
    window.invalidate_worker_token()
    window.editor_load_jobs.next()
    window.editor_load_jobs.activity_tokens.clear()
    window.midi_preview_jobs.next()
    if path is None:
        window.drop_zone.reset_prompt()
    window.current_result = None
    window.current_stems = []
    window.current_input_stem = None
    window.base_editor_project = None
    window.editor_project = None
    window.manual_chords = []
    window.removed_chord_ranges = []
    window.chord_note_overrides = {}
    window.chord_note_filter_context = None
    window.current_chord_base_weights = {}
    window.current_harmony_context = None
    window.current_theory_analysis = None
    window.current_chord_gap_analysis = None
    with blocked_signals(window.notation_spelling):
        window.notation_spelling.setCurrentIndex(0)
    window.rendering_midi_previews.clear()
    window.clear_transport_players()
    window.track_audio_checks.clear()
    window.track_audio_sliders.clear()
    window.track_midi_checks.clear()
    window.track_midi_sliders.clear()
    window.track_analysis_checks.clear()
    window.track_control_panels.clear()
    window.track_control_detail_rows.clear()
    window.track_control_top_spacer = None
    window.track_control_bottom_spacer = None
    window.hidden_track_status = None
    window.latest_output_dir = None
    window.run_midi.setEnabled(False)
    window.export_button.setEnabled(False)
    if getattr(window, "export_action", None) is not None:
        window.export_action.setEnabled(False)
    window.separation_status.setText("Not run yet.")
    window.midi_status.setText("Run the full pipeline first, then MIDI can be rerun without separating again.")
    window.editor_summary.setText(EMPTY_EDITOR_SUMMARY)
    window.fit_song_button.setEnabled(False)
    window.fit_review_button.setEnabled(False)
    window.play_review_button.setEnabled(False)
    window.previous_chord_button.setEnabled(False)
    window.next_chord_button.setEnabled(False)
    window.delete_chord_button.setEnabled(False)
    window.inspect_chord_button.setEnabled(False)
    window.inspect_theory_button.setEnabled(False)
    window.use_gap_suggestion_button.setEnabled(False)
    window.inspect_gap_suggestion_button.setEnabled(False)
    window.editor_position.setText(format_time(0))
    window.current_chord.setText("Harmony: -")
    window.set_chord_context_text("Sample: -")
    window.set_theory_analysis(None)
    window.set_gap_analysis(None)
    window.reset_activity("Ready for new audio")
    window.note_filter_list.clear()
    window.track_visibility_checks.clear()
    window.track_note_counts.clear()
    window.editor_track_visibility = {}
    clear_layout(window.playback_controls)
    window.chord_list.clear()
    window.refresh_chord_keyboard()
    window.timeline.set_project(None)


def open_latest_output(window) -> None:
    target = window.latest_output_dir or Path(window.output_dir.text())
    window.open_folder_path(target, "output folder")


def open_logs_folder(window) -> None:
    window.open_folder_path(logs_dir(), "logs folder")


def open_folder_path(window, target: Path, label: str) -> None:
    try:
        opened = open_folder(target)
    except Exception as exc:
        window.logger.exception("Could not open %s: %s", label, target)
        window.append_log(f"Could not open {label}: {exc}")
        window.statusBar().showMessage(f"Could not open {label}. See logs for details.", 6000)
        return
    window.statusBar().showMessage(f"Opened {label}: {opened}", 3000)
