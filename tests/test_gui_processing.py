from __future__ import annotations

import queue
from pathlib import Path

import pitchstems.gui_processing as gui_processing
from pitchstems.gui_jobs import WorkerJobState
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
    assert window.messages.get_nowait() == ("ENABLE_PROCESS", 3, "cancelled")


class _FlushWindow:
    def __init__(self) -> None:
        self.logger = _Logger()
        self.messages: queue.Queue[object] = queue.Queue()
        self.worker_jobs = WorkerJobState()
        self.worker_jobs.active_token = 7
        self.results: list[PipelineResult] = []
        self.logs: list[str] = []
        self.processing_states: list[bool] = []
        self.activity_messages: list[str] = []

    def is_active_worker_token(self, token: int) -> bool:
        return self.worker_jobs.is_active(token)

    def set_current_result(self, result: PipelineResult) -> None:
        self.results.append(result)

    def append_log(self, message: str) -> None:
        self.logs.append(message)

    def set_activity_message(self, message: str) -> None:
        self.activity_messages.append(message)

    def set_processing_state(self, busy: bool) -> None:
        self.processing_states.append(busy)

    def end_activity(self, message: str = "Ready") -> None:
        self.activity_messages.append(message)


def test_flush_messages_reports_cancelled_completion_without_success_text(tmp_path: Path) -> None:
    window = _FlushWindow()
    window.messages.put(("WORKER_LOG", 7, "Processing cancelled."))
    window.messages.put(("ENABLE_PROCESS", 7, "cancelled"))

    gui_processing.flush_messages(window)

    assert window.logs == ["Processing cancelled."]
    assert window.processing_states == [False]
    assert window.activity_messages[-1] == "Processing cancelled"
    assert window.worker_jobs.active_token is None


def test_flush_messages_reports_error_completion_without_success_text(tmp_path: Path) -> None:
    window = _FlushWindow()
    window.messages.put(("WORKER_LOG", 7, "Error: boom"))
    window.messages.put(("ENABLE_PROCESS", 7, "error"))

    gui_processing.flush_messages(window)

    assert window.logs == ["Error: boom"]
    assert window.processing_states == [False]
    assert window.activity_messages[-1] == "Processing failed"
    assert window.worker_jobs.active_token is None
