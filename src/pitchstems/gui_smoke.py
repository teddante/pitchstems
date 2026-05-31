from __future__ import annotations

import tempfile
import time
import wave
from pathlib import Path

from mido import Message, MetaMessage, MidiFile, MidiTrack
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from pitchstems.editor_loader import EditorLoadResult
from pitchstems.pipeline import PipelineResult
from pitchstems.project_store import save_project_manifest
from pitchstems.separation import StemResult
from pitchstems.transcription import MidiResult


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
    _assert(not window.stop_button.isEnabled(), "stop disabled before playback")
    _assert(not window.fit_song_button.isEnabled(), "fit disabled before project load")
    _assert(window.editor_position.text() == "00:00.000", "initial editor position")

    window.main_tabs.setCurrentIndex(tab_names.index("Pipeline"))
    _assert(window.run_full.isEnabled(), "run button enabled")
    _assert(not window.run_midi.isEnabled(), "rerun midi disabled before project load")
    _assert(window.generate_midi.isChecked(), "generate MIDI default")
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
    _assert(window.timeline_slider.isEnabled(), "timeline slider enabled")
    _assert(window.fit_song_button.isEnabled(), "fit song enabled")
    _assert(window.run_midi.isEnabled(), "rerun midi enabled after project load")
    _assert("bass" in window.track_analysis_checks, "bass chord analysis control")
    _assert(window.track_analysis_checks["bass"].isChecked(), "bass chord analysis enabled")
    _assert("bass" in window.track_visibility_checks, "bass visibility control")
    _assert(window.track_visibility_checks["bass"].isChecked(), "bass visible")

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
    report = window.current_chord_analysis_report()
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

    window.fit_editor_song_to_view()
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
    window.active_worker_token = 7
    window.open_project_manifest(second_manifest_path)
    _wait_for(
        lambda: window.current_result is not None
        and window.current_result.project_dir == second_manifest_path.parent
        and window.editor_project is not None,
        "second editor project load",
    )
    _assert(window.active_worker_token is None, "project open invalidates active worker")
    _assert(not window.transport.is_playing, "project open stops old transport")
    _assert(not window.transport_timer.isActive(), "project open stops old transport timer")
    _assert(window.play_button.text() == "Play", "project open resets play button")
    _assert(not window.stop_button.isEnabled(), "project open disables stop button")
    _assert("piano" in window.track_analysis_checks, "second project track controls")
    _assert("bass" not in window.track_analysis_checks, "old project track controls cleared")
    _assert(set(window.timeline.visible_tracks) == {"piano"}, "timeline visible tracks switched")
    _assert(window.timeline.selection_range() is None, "timeline selection reset on project switch")
    active_project_dir = window.current_result.project_dir
    window.active_worker_token = 10
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
    window.active_worker_token = None
    _assert(window.current_result.project_dir == active_project_dir, "stale worker result ignored")
    activity_label = window.activity_label.text()
    window.messages.put(("ENABLE_PROCESS", 9))
    window.flush_messages()
    _assert(window.activity_label.text() == activity_label, "stale worker completion ignored")
    stale_preview = active_project_dir / "editor" / "midi-preview" / "piano_midi_preview.wav"
    window.messages.put(("MIDI_PREVIEWS", window.midi_preview_token - 1, active_project_dir, {"piano"}, {"piano": stale_preview}))
    window.flush_messages()
    _assert("piano" not in window.transport.midi_preview_paths, "stale MIDI preview ignored")
    stale_token = window.midi_preview_token - 1
    current_token = window.midi_preview_token
    current_worker = _FakeWorker(alive=True)
    worker_key = (active_project_dir, "piano")
    window.midi_preview_workers[worker_key] = (stale_token, _FakeWorker(alive=True))
    _assert(
        not window._midi_preview_worker_running(active_project_dir, "piano"),
        "stale MIDI preview worker does not block current project",
    )
    window.midi_preview_workers[worker_key] = (current_token, current_worker)
    window.messages.put(("MIDI_PREVIEWS", stale_token, active_project_dir, {"piano"}, {"piano": stale_preview}))
    window.flush_messages()
    _assert(
        window.midi_preview_workers.get(worker_key) == (current_token, current_worker),
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
    window.finish_editor_project_load(window.editor_load_token - 1, stale_loaded)
    _assert(window.activity_label.text() == activity_label, "stale editor load leaves activity label alone")

    window.reset_stage_state()
    _assert(window.current_result is None, "reset clears current result")
    _assert(window.editor_project is None, "reset clears editor project")
    _assert(window.timeline.project is None, "reset clears timeline project")
    _assert(not window.track_analysis_checks, "reset clears track controls")
    _assert(not window.run_midi.isEnabled(), "reset disables rerun MIDI")


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
