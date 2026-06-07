from __future__ import annotations

import queue
from pathlib import Path

import pitchstems.gui_processing as gui_processing
from pitchstems.pipeline import PipelineCancelledError, PipelineResult
from pitchstems.separation import StemResult
from pitchstems.transcription import MidiOptions


class _Logger:
    def info(self, *_args, **_kwargs) -> None:
        pass

    def exception(self, *_args, **_kwargs) -> None:
        raise AssertionError("cancellation should not be logged as an exception")


class _Window:
    def __init__(self) -> None:
        self.logger = _Logger()
        self.messages: queue.Queue[object] = queue.Queue()


def test_run_midi_stage_reports_cancellation_without_error(monkeypatch, tmp_path: Path) -> None:
    def cancelled_midi_stage(**_kwargs):
        raise PipelineCancelledError("Processing cancelled.")

    monkeypatch.setattr(gui_processing, "process_midi_from_stems", cancelled_midi_stage)
    result = PipelineResult(
        project_dir=tmp_path / "song.pitchstems",
        normalized_audio=tmp_path / "song.pitchstems" / "work" / "song.wav",
        stems=[StemResult("bass", tmp_path / "song.pitchstems" / "stems" / "bass.wav")],
        midi_files=[],
        combined_midi=None,
        zip_path=None,
    )
    request = gui_processing.MidiRunRequest(
        result=result,
        input_stem="song",
        stems=result.stems,
        midi_options=MidiOptions(),
        midi_stems={"bass"},
        create_zip=False,
        cancelled=lambda: True,
    )
    window = _Window()

    gui_processing.run_midi_stage(window, 3, request)

    assert window.messages.get_nowait() == ("WORKER_LOG", 3, "Processing cancelled.")
    assert window.messages.get_nowait() == ("ENABLE_PROCESS", 3)
