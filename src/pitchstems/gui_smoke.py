from __future__ import annotations

import tempfile
import time
import wave
from pathlib import Path

from mido import Message, MetaMessage, MidiFile, MidiTrack
from PySide6.QtWidgets import QApplication

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
    _assert("drums" in window.midi_stem_checks, "MIDI stem checks populated")
    _assert(not window.midi_stem_checks["drums"].isChecked(), "drums MIDI default off")

    menu_titles = {action.text() for action in window.menuBar().actions()}
    _assert("&File" in menu_titles, "file menu")
    _assert("&Run" in menu_titles, "run menu")
    _assert("&View" in menu_titles, "view menu")
    _assert("&Help" in menu_titles, "help menu")
    _assert(window.recent_projects_menu is not None, "recent projects menu created")

    window.show_timeline_controls()
    _assert("Timeline controls:" in window.statusBar().currentMessage(), "timeline controls status")


def run_project_smoke(window) -> None:
    manifest_path = _create_smoke_project()
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

    window.fit_editor_song_to_view()
    _assert(window.timeline.horizontalScrollBar().value() == 0, "fit song horizontal start")
    toggle_row, audio_row, midi_row = window.track_control_detail_rows["bass"]
    _assert(toggle_row.isVisible(), "fit song track toggles visible")
    _assert(audio_row.isVisible(), "fit song audio volume visible")
    _assert(midi_row.isVisible(), "fit song midi volume visible")
    _assert(window.save_editor_state(), "editor state save")


def _create_smoke_project() -> Path:
    root = Path(tempfile.mkdtemp(prefix="pitchstems-gui-smoke-"))
    project_dir = root / "smoke.pitchstems"
    normalized = project_dir / "work" / "song.wav"
    stem = project_dir / "stems" / "bass.wav"
    midi = project_dir / "midi" / "bass.mid"
    for audio_path in [normalized, stem]:
        _write_wav(audio_path, duration_seconds=2.0)
    _write_midi(midi)
    result = PipelineResult(
        project_dir=project_dir,
        normalized_audio=normalized,
        stems=[StemResult("bass", stem)],
        midi_files=[MidiResult("bass", midi)],
        combined_midi=None,
        zip_path=None,
        source_audio=normalized,
    )
    return save_project_manifest(
        result,
        midi_stems={"bass"},
        generate_midi=True,
        midi_policy="pitched",
        create_zip=False,
        track_visibility={"bass": True},
        track_analysis_enabled={"bass": True},
        track_audio_enabled={"bass": True},
        track_audio_volume={"bass": 80},
        track_midi_enabled={"bass": False},
        track_midi_volume={"bass": 70},
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


def _write_midi(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    midi = MidiFile(ticks_per_beat=480)
    track = MidiTrack()
    track.append(MetaMessage("set_tempo", tempo=500000, time=0))
    for note in [43, 47, 50]:
        track.append(Message("note_on", note=note, velocity=96, time=0))
    track.append(Message("note_off", note=43, velocity=0, time=960))
    track.append(Message("note_off", note=47, velocity=0, time=0))
    track.append(Message("note_off", note=50, velocity=0, time=0))
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


def _assert(condition: bool, label: str) -> None:
    if not condition:
        raise RuntimeError(f"GUI startup smoke failed: {label}")
