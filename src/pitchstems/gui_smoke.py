from __future__ import annotations

import os
import tempfile
import time
import wave
from pathlib import Path

from mido import Message, MetaMessage, MidiFile, MidiTrack
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from pitchstems.editor_loader import EditorLoadResult
from pitchstems.export_files import build_export_items, copy_export_items
from pitchstems import gui_editor_actions
from pitchstems.pipeline_models import MidiResult, PipelineResult, StemResult
from pitchstems.project_store import save_project_manifest
from pitchstems.harmony_report import current_chord_analysis_report


def run_startup_smoke(window) -> None:
    _assert(window.windowTitle() == "PitchStems", "window title")
    _assert(window.main_tabs.count() >= 2, "main tabs")
    tab_names = [window.main_tabs.tabText(index) for index in range(window.main_tabs.count())]
    _assert("Pipeline" in tab_names, "pipeline tab")
    _assert("Editor" in tab_names, "editor tab")

    window.main_tabs.setCurrentIndex(tab_names.index("Editor"))
    _assert(window.timeline.project is None, "empty startup timeline")
    _assert(window.play_button.isEnabled(), "play available before project load")
    _assert(window.play_button.text() == "Play", "play button text")
    _assert(not window.play_review_button.isEnabled(), "play review disabled before project load")
    _assert(not window.previous_chord_button.isEnabled(), "previous chord disabled before project load")
    _assert(not window.next_chord_button.isEnabled(), "next chord disabled before project load")
    _assert(not window.stop_button.isEnabled(), "stop disabled before playback")
    _assert(not window.fit_song_button.isEnabled(), "fit disabled before project load")
    _assert(window.editor_position.text() == "00:00.000", "initial editor position")
    _assert(not hasattr(window, "timeline_slider"), "no hidden timeline slider")
    _assert(window.drop_zone.maximumHeight() > 1000, "drop zone can grow with content")
    _assert(window.note_filter_list.maximumHeight() > 1000, "note evidence list can grow")
    _assert(window.piano_chord_view.maximumHeight() > 1000, "piano view can grow")

    window.main_tabs.setCurrentIndex(tab_names.index("Pipeline"))
    _assert(window.run_full.isEnabled(), "run button enabled")
    _assert(not window.run_midi.isEnabled(), "rerun midi disabled before project load")
    _assert(not window.export_button.isEnabled(), "export disabled before project load")
    _assert(not hasattr(window, "create_zip"), "GUI ZIP checkbox removed")
    _assert(window.generate_midi.isChecked(), "generate MIDI default")
    _assert(set(window.workspace_nav_buttons) == {"Pipeline", "Editor"}, "workspace nav maps to real pages")
    _assert(not hasattr(window, "model_select"), "GUI model selector removed")
    _assert(not hasattr(window, "model_title"), "redundant model title label removed")
    _assert(window.separation_card.title(), "model title displayed on separation card")
    _assert(window.processing_tabs.count() == 2, "pipeline processing tabs")
    _assert(window.processing_tabs.tabText(0) == "Basic Pitch", "basic pitch tab")
    _assert(window.processing_tabs.tabText(1) == "Runtime", "runtime tab")
    _assert("drums" in window.midi_stem_checks, "MIDI stem checks populated")
    _assert(not window.midi_stem_checks["drums"].isChecked(), "drums MIDI default off")
    window.start_full_processing()
    _assert("Drop an audio file first." in window.log.toPlainText(), "empty full run guidance")
    window.start_midi_processing()
    _assert("Run separation first." in window.log.toPlainText(), "empty MIDI rerun guidance")

    menu_titles = {action.text() for action in window.menuBar().actions()}
    _assert("&File" in menu_titles, "file menu")
    _assert("&Run" in menu_titles, "run menu")
    _assert("&View" in menu_titles, "view menu")
    _assert("&Help" in menu_titles, "help menu")
    _assert(window.recent_projects_menu is not None, "recent projects menu created")

    window.show_timeline_controls()
    _assert("Timeline controls:" in window.statusBar().currentMessage(), "timeline controls status")


def run_project_smoke(window) -> None:
    manifest_path = _create_smoke_project(stem_name="bass", pitches=[43, 47, 50])
    window.open_project_manifest(manifest_path)
    _wait_for(lambda: window.editor_project is not None, "editor project load")

    _assert(window.current_result is not None, "current result after project open")
    _assert(window.timeline.project is window.editor_project, "timeline project attached")
    _assert(window.fit_song_button.isEnabled(), "fit song enabled")
    _assert(window.fit_review_button.isEnabled(), "fit review enabled")
    _assert(window.play_review_button.isEnabled(), "play review enabled")
    _assert(window.previous_chord_button.isEnabled(), "previous chord enabled")
    _assert(window.next_chord_button.isEnabled(), "next chord enabled")
    _assert(window.run_midi.isEnabled(), "rerun midi enabled after project load")
    _assert(window.export_button.isEnabled(), "export enabled after project load")
    _assert("bass" in window.track_analysis_checks, "bass chord analysis control")
    _assert(window.track_analysis_checks["bass"].isChecked(), "bass chord analysis enabled")
    _assert("bass" in window.track_visibility_checks, "bass visibility control")
    _assert(window.track_visibility_checks["bass"].isChecked(), "bass visible")

    window.next_chord_button.click()
    QApplication.processEvents()
    _assert(window.timeline.selected_chord is not None, "next chord button selects a chord")
    _assert(window.timeline.position == window.timeline.selected_chord.start, "next chord button moves playhead")
    window.clear_editor_selection()

    window.timeline._set_selection(0.0, 1.0, notify=True)
    _assert(window.timeline.selection_range() == (0.0, 1.0), "timeline selection")
    window.refresh_current_harmony(0.5)
    _assert(window.current_harmony_context is not None, "harmony context")
    _assert("Sample:" in window.chord_context.text(), "chord sample text")
    flat_index = window.notation_spelling.findData("flat")
    _assert(flat_index >= 0, "flat notation option")
    window.notation_spelling.setCurrentIndex(flat_index)
    QApplication.processEvents()
    _assert(window.timeline.note_name_formatter(66).startswith("Gb"), "timeline follows flat notation")
    window.chord_list.setCurrentRow(0)
    window.assign_selected_chord_to_selection()
    _assert(bool(window.manual_chords), "assign chord from inspector to timeline selection")
    assigned_chord = window.manual_chords[-1]
    window.timeline.clear_selection()
    window.timeline.selected_chord = assigned_chord
    window.chord_list.setCurrentRow(0)
    window.refresh_chord_actions()
    _assert(window.use_chord_button.text() == "Use for Chord", "selected chord correction action")
    _assert(window.delete_chord_button.isEnabled(), "selected chord delete action")
    window.set_editor_position_seconds(
        assigned_chord.end + 0.25,
        save=False,
        seek_players=False,
        force_harmony_refresh=True,
    )
    _assert(
        window.loop_playback_start_seconds() == assigned_chord.start,
        "selected chord playback loops from chord start",
    )
    _assert(window.current_chord.text().startswith("Selected chord:"), "selected chord drives harmony review")
    window.assign_selected_chord_to_selection()
    _assert(bool(window.manual_chords), "assign chord from inspector to selected chord")
    corrected_chord = window.manual_chords[-1]
    window.timeline.selected_chord = corrected_chord
    window.refresh_chord_actions()
    window.delete_chord_button.click()
    QApplication.processEvents()
    _assert(corrected_chord not in window.manual_chords, "delete chord button removes selected manual chord")
    _assert(window.timeline.selected_chord is None, "delete chord button clears selected chord")
    window.timeline._set_selection(0.25, 0.75, notify=True)
    window.refresh_chord_actions()
    _assert(window.timeline.selected_chord is None, "range selection clears selected chord")
    _assert(window.use_chord_button.text() == "Use for Selection", "range selection becomes correction target")
    _assert(not window.delete_chord_button.isEnabled(), "range selection disables delete chord")
    window.fit_review_button.click()
    QApplication.processEvents()
    _assert(window.statusBar().currentMessage() == "Timeline fit to review target.", "fit review button")
    window.play_review_button.click()
    QApplication.processEvents()
    _assert(window.transport.is_playing, "play review starts transport")
    _assert(window.timeline.position == 0.25, "play review starts at selected range")
    _assert(window.play_button.text() == "Pause", "play review changes play button")
    window.stop_transport()
    QApplication.processEvents()
    window.clear_editor_selection()
    _assert(window.timeline.selected_chord is None, "clear selection clears selected chord")
    report = current_chord_analysis_report(window)
    _assert("Harmony Inspector Calculation" in report, "harmony report title")
    _assert("MIDI Energy Evidence" in report, "harmony report evidence section")
    note_item = window.note_filter_list.item(0)
    _assert(note_item is not None, "note evidence list populated")
    note_pitch_class = int(note_item.data(Qt.UserRole))
    note_item.setCheckState(Qt.Checked)
    QApplication.processEvents()
    _assert(window.chord_note_overrides.get(note_pitch_class) == "force", "note evidence force override")
    note_item = window.note_filter_list.item(0)
    note_item.setCheckState(Qt.PartiallyChecked)
    QApplication.processEvents()
    _assert(note_pitch_class not in window.chord_note_overrides, "note evidence auto override")

    gui_editor_actions.fit_editor_song_to_view(window)
    _assert(window.timeline.horizontalScrollBar().value() == 0, "fit song horizontal start")
    toggle_row, audio_row, midi_row = window.track_control_detail_rows["bass"]
    _assert(toggle_row.isVisible(), "fit song track toggles visible")
    _assert(audio_row.isVisible(), "fit song audio volume visible")
    _assert(midi_row.isVisible(), "fit song midi volume visible")
    window.track_visibility_checks["bass"].setChecked(False)
    QApplication.processEvents()
    _assert("bass" not in window.timeline.visible_tracks, "view toggle hides timeline track")
    _assert(not window.track_control_panels["bass"].isVisible(), "view toggle hides track controls row")
    window.show_all_timeline_tracks()
    QApplication.processEvents()
    _assert("bass" in window.timeline.visible_tracks, "show all restores timeline track")
    _assert(window.track_control_panels["bass"].isVisible(), "show all restores track controls row")
    window.track_analysis_checks["bass"].setChecked(False)
    QApplication.processEvents()
    _assert("bass" not in (window.current_harmony_context.sampled_tracks if window.current_harmony_context else ()), "chord toggle removes sampled track")
    window.track_analysis_checks["bass"].setChecked(True)
    QApplication.processEvents()
    _assert("bass" in (window.current_harmony_context.sampled_tracks if window.current_harmony_context else ()), "chord toggle restores sampled track")
    window.track_audio_checks["bass"].setChecked(False)
    window.track_audio_sliders["bass"].setValue(25)
    QApplication.processEvents()
    _assert(not window.track_audio_checks["bass"].isChecked(), "audio toggle state")
    _assert(window.track_audio_sliders["bass"].value() == 25, "audio volume state")
    window.track_audio_checks["bass"].setChecked(True)
    original_preview_renderer = window.start_midi_preview_render
    window.start_midi_preview_render = lambda *_args, **_kwargs: None
    window.track_midi_checks["bass"].setChecked(True)
    QApplication.processEvents()
    _assert(window.midi_track_enabled("bass"), "MIDI toggle enables transport state")
    window.track_midi_checks["bass"].setChecked(False)
    window.start_midi_preview_render = original_preview_renderer
    QApplication.processEvents()
    _assert(not window.midi_track_enabled("bass"), "MIDI toggle disables transport state")
    window.play_transport()
    QApplication.processEvents()
    _assert(window.transport.is_playing, "play starts transport")
    _assert(window.play_button.text() == "Pause", "play button changes to pause")
    _assert(window.stop_button.isEnabled(), "stop enabled during playback")
    window.stop_transport()
    QApplication.processEvents()
    _assert(not window.transport.is_playing, "stop clears transport playing state")
    _assert(window.play_button.text() == "Play", "stop resets play button")
    _assert(not window.stop_button.isEnabled(), "stop disabled after stop")
    _assert(window.save_editor_state(), "editor state save")

    second_manifest_path = _create_smoke_project(stem_name="piano", pitches=[60, 64, 67])
    window.transport.is_playing = True
    window.play_button.setText("Pause")
    window.stop_button.setEnabled(True)
    window.transport_timer.start(80)
    window.worker_jobs.active_token = 7
    window.open_project_manifest(second_manifest_path)
    _wait_for(
        lambda: window.current_result is not None
        and window.current_result.project_dir == second_manifest_path.parent
        and window.editor_project is not None,
        "second editor project load",
    )
    _assert(window.worker_jobs.active_token is None, "project open invalidates active worker")
    _assert(not window.transport.is_playing, "project open stops old transport")
    _assert(not window.transport_timer.isActive(), "project open stops old transport timer")
    _assert(window.play_button.text() == "Play", "project open resets play button")
    _assert(not window.stop_button.isEnabled(), "project open disables stop button")
    _assert("piano" in window.track_analysis_checks, "second project track controls")
    _assert("bass" not in window.track_analysis_checks, "old project track controls cleared")
    _assert(set(window.timeline.visible_tracks) == {"piano"}, "timeline visible tracks switched")
    _assert(window.timeline.selection_range() is None, "timeline selection reset on project switch")
    active_project_dir = window.current_result.project_dir
    window.worker_jobs.active_token = 10
    window.messages.put(
        (
            "RESULT",
            9,
            PipelineResult(
                project_dir=manifest_path.parent,
                normalized_audio=manifest_path.parent / "work" / "song.wav",
                stems=[],
                midi_files=[],
                combined_midi=None,
                zip_path=None,
            ),
        )
    )
    window.flush_messages()
    window.worker_jobs.active_token = None
    _assert(window.current_result.project_dir == active_project_dir, "stale worker result ignored")
    activity_label = window.activity_label.text()
    window.messages.put(("ENABLE_PROCESS", 9))
    window.flush_messages()
    _assert(window.activity_label.text() == activity_label, "stale worker completion ignored")
    stale_preview = active_project_dir / "editor" / "midi-preview" / "piano_midi_preview.wav"
    window.messages.put(("MIDI_PREVIEWS", window.midi_preview_jobs.token - 1, active_project_dir, {"piano"}, {"piano": stale_preview}))
    window.flush_messages()
    _assert("piano" not in window.transport.midi_preview_paths, "stale MIDI preview ignored")
    stale_token = window.midi_preview_jobs.token - 1
    current_token = window.midi_preview_jobs.token
    current_worker = _FakeWorker(alive=True)
    worker_key = (active_project_dir, "piano")
    window.midi_preview_jobs.workers[worker_key] = (stale_token, _FakeWorker(alive=True))
    _assert(
        not window._midi_preview_worker_running(active_project_dir, "piano"),
        "stale MIDI preview worker does not block current project",
    )
    window.midi_preview_jobs.workers[worker_key] = (current_token, current_worker)
    window.messages.put(("MIDI_PREVIEWS", stale_token, active_project_dir, {"piano"}, {"piano": stale_preview}))
    window.flush_messages()
    _assert(
        window.midi_preview_jobs.workers.get(worker_key) == (current_token, current_worker),
        "stale MIDI preview completion does not clear current worker",
    )
    stale_loaded = EditorLoadResult(
        pipeline_result=window.current_result,
        base_project=window.base_editor_project,
        editor_project=window.editor_project,
        editor_state={},
        manual_chords=[],
        removed_chord_ranges=[],
    )
    window.finish_editor_project_load(window.editor_load_jobs.token - 1, stale_loaded)
    _assert(window.activity_label.text() == activity_label, "stale editor load leaves activity label alone")

    window.reset_stage_state()
    _assert(window.current_result is None, "reset clears current result")
    _assert(window.editor_project is None, "reset clears editor project")
    _assert(window.timeline.project is None, "reset clears timeline project")
    _assert(not window.track_analysis_checks, "reset clears track controls")
    _assert(not window.run_midi.isEnabled(), "reset disables rerun MIDI")
    _assert(not window.fit_review_button.isEnabled(), "reset disables fit review")
    _assert(not window.play_review_button.isEnabled(), "reset disables play review")
    _assert(not window.previous_chord_button.isEnabled(), "reset disables previous chord")
    _assert(not window.next_chord_button.isEnabled(), "reset disables next chord")
    _assert(not window.delete_chord_button.isEnabled(), "reset disables delete chord")


def run_real_audio_project_smoke(window, manifest_path: Path) -> None:
    window.open_project_manifest(manifest_path)
    _wait_for(lambda: window.editor_project is not None, "real-audio editor project load")

    _assert(window.current_result is not None, "real-audio current result")
    _assert(window.current_result.source_audio is not None, "real-audio source import recorded")
    _assert(window.current_result.source_audio.is_file(), "real-audio source import exists")
    _assert(window.current_result.stems, "real-audio separated stems")
    _assert(any(stem.path.is_file() for stem in window.current_result.stems), "real-audio stem files")
    _assert(window.current_result.midi_files, "real-audio MIDI files")
    _assert(any(midi.path.is_file() for midi in window.current_result.midi_files), "real-audio MIDI files exist")
    _assert(window.timeline.project is window.editor_project, "real-audio timeline project attached")

    gui_editor_actions.fit_editor_song_to_view(window)
    window.timeline._set_selection(0.0, min(1.0, max(0.1, window.editor_project.duration)), notify=True)
    window.refresh_current_harmony(0.0)
    _assert(window.current_harmony_context is not None, "real-audio harmony review context")

    _assert(window.play_review_button.isEnabled(), "real-audio play review enabled")
    gui_editor_actions.play_editor_review_target(window)
    QApplication.processEvents()
    _assert(window.transport.is_playing, "real-audio review playback starts")
    _assert(window.timeline.position == 0.0, "real-audio review playback starts at selection")
    window.stop_transport()
    QApplication.processEvents()
    _assert(not window.transport.is_playing, "real-audio review playback stops")

    items = build_export_items(window.current_result)
    _assert(items, "real-audio selected export items")
    default_items = [item for item in items if item.default_selected]
    default_categories = {item.category for item in default_items}
    _assert("Project" in default_categories, "real-audio selected export includes project manifest")
    _assert("Stems" in default_categories, "real-audio selected export includes stems")
    _assert(
        bool(default_categories & {"MIDI", "Combined MIDI"}),
        "real-audio selected export includes MIDI",
    )
    _assert(
        "Source Audio" not in default_categories,
        "real-audio selected export keeps source audio unchecked by default",
    )
    export_dir = Path(
        os.environ.get("PITCHSTEMS_REAL_AUDIO_EXPORT_DIR")
        or tempfile.mkdtemp(prefix="pitchstems-real-audio-export-")
    )
    summary = copy_export_items(default_items, export_dir)
    _assert(summary.file_count > 0, "real-audio selected export copied files")
    _assert(any(summary.destination.rglob("*")), "real-audio selected export artifacts exist")
    copied_paths = {path.as_posix() for path in summary.relative_paths}
    _assert("pitchstems.project.json" in copied_paths, "real-audio copied project manifest")
    _assert(any(path.startswith("stems/") for path in copied_paths), "real-audio copied stem export")
    _assert(any(path.startswith("midi/") for path in copied_paths), "real-audio copied MIDI export")
    _assert(
        not any(path.startswith("audio/") for path in copied_paths),
        "real-audio did not copy source audio by default",
    )


def capture_visual_audit(window, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    captures: list[Path] = []
    tab_names = [window.main_tabs.tabText(index) for index in range(window.main_tabs.count())]
    for width, height in [(1220, 780), (900, 700)]:
        window.resize(width, height)
        for tab_name in ["Pipeline", "Editor"]:
            window.main_tabs.setCurrentIndex(tab_names.index(tab_name))
            QApplication.processEvents()
            path = output_dir / f"{tab_name.lower()}-{width}x{height}.png"
            window.grab().save(str(path))
            captures.append(path)
    return captures


def _create_smoke_project(stem_name: str, pitches: list[int]) -> Path:
    root = Path(tempfile.mkdtemp(prefix="pitchstems-gui-smoke-"))
    project_dir = root / "smoke.pitchstems"
    normalized = project_dir / "work" / "song.wav"
    stem = project_dir / "stems" / f"{stem_name}.wav"
    midi = project_dir / "midi" / f"{stem_name}.mid"
    for audio_path in [normalized, stem]:
        _write_wav(audio_path, duration_seconds=2.0)
    _write_midi(midi, pitches)
    result = PipelineResult(
        project_dir=project_dir,
        normalized_audio=normalized,
        stems=[StemResult(stem_name, stem)],
        midi_files=[MidiResult(stem_name, midi)],
        combined_midi=None,
        zip_path=None,
        source_audio=normalized,
    )
    return save_project_manifest(
        result,
        midi_stems={stem_name},
        generate_midi=True,
        midi_policy="pitched",
        create_zip=False,
        track_visibility={stem_name: True},
        track_analysis_enabled={stem_name: True},
        track_audio_enabled={stem_name: True},
        track_audio_volume={stem_name: 80},
        track_midi_enabled={stem_name: False},
        track_midi_volume={stem_name: 70},
        notation_spelling="auto",
        playhead_seconds=0.0,
    )


def _write_wav(path: Path, duration_seconds: float, sample_rate: int = 8000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = int(duration_seconds * sample_rate)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(b"\x00\x00" * frames)


def _write_midi(path: Path, pitches: list[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    midi = MidiFile(ticks_per_beat=480)
    track = MidiTrack()
    track.append(MetaMessage("set_tempo", tempo=500000, time=0))
    for note in pitches:
        track.append(Message("note_on", note=note, velocity=96, time=0))
    for index, note in enumerate(pitches):
        track.append(Message("note_off", note=note, velocity=0, time=960 if index == 0 else 0))
    midi.tracks.append(track)
    midi.save(path)


def _wait_for(predicate, label: str, timeout_seconds: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return
        time.sleep(0.02)
    raise RuntimeError(f"GUI startup smoke failed: timed out waiting for {label}")


class _FakeWorker:
    def __init__(self, alive: bool) -> None:
        self.alive = alive

    def is_alive(self) -> bool:
        return self.alive


def _assert(condition: bool, label: str) -> None:
    if not condition:
        raise RuntimeError(f"GUI startup smoke failed: {label}")
