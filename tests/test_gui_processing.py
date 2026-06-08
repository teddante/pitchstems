from __future__ import annotations

import queue
from pathlib import Path

import pitchstems.gui_processing as gui_processing
import pitchstems.gui_shutdown as gui_shutdown
from pitchstems.gui_jobs import EditorLoadJobState, MidiPreviewJobState, WorkerJobState
from pitchstems.pipeline import PipelineCancelledError, PipelineResult
from pitchstems.separation import StemResult
from pitchstems.transcription import MidiOptions


class _Logger:
    def info(self, *_args, **_kwargs) -> None:
        pass

    def exception(self, *_args, **_kwargs) -> None:
        raise AssertionError("cancellation should not be logged as an exception")


class _LiveWorker:
    def is_alive(self) -> bool:
        return True


class _Window:
    def __init__(self) -> None:
        self.logger = _Logger()
        self.messages: queue.Queue[object] = queue.Queue()


class DummyWindow:
    def __init__(self) -> None:
        self.worker_jobs = WorkerJobState()
        self.activities: list[str] = []
        self.logs: list[str] = []

    def set_activity_message(self, message: str) -> None:
        self.activities.append(message)

    def append_log(self, message: str) -> None:
        self.logs.append(message)


class _InvalidInputWindow:
    def __init__(self, path: Path) -> None:
        self.worker = None
        self.drop_zone = type("DropZone", (), {"path": path})()
        self.logs: list[str] = []

    def append_log(self, message: str) -> None:
        self.logs.append(message)


def test_start_full_processing_rejects_invalid_audio_path(tmp_path: Path) -> None:
    window = _InvalidInputWindow(tmp_path)

    gui_processing.start_full_processing(window)

    assert window.logs == ["Choose an audio file, not a folder."]


def test_native_process_jobs_are_opt_in(monkeypatch) -> None:
    monkeypatch.delenv("PITCHSTEMS_NATIVE_PROCESS_JOBS", raising=False)
    assert gui_processing.use_native_process_jobs() is False
    monkeypatch.setenv("PITCHSTEMS_NATIVE_PROCESS_JOBS", "1")
    assert gui_processing.use_native_process_jobs() is True


def test_cancel_processing_requests_active_worker_and_updates_activity() -> None:
    window = DummyWindow()
    token = window.worker_jobs.start()

    assert gui_processing.cancel_processing(window) is True
    assert window.worker_jobs.is_cancel_requested(token)
    assert window.activities[-1] == "Cancelling after the current model stage..."
    assert "Cancellation requested." in window.logs[-1]


def test_cancel_processing_reports_no_active_worker() -> None:
    window = DummyWindow()

    assert gui_processing.cancel_processing(window) is False
    assert "No active processing job to cancel." in window.logs[-1]


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
        self.worker = _LiveWorker()
        self.close_after_worker = False
        self.closed = False
        self.close_attempts = 0
        self.results: list[PipelineResult] = []
        self.logs: list[str] = []
        self.processing_states: list[bool] = []
        self.activity_messages: list[str] = []
        self.editor_load_jobs = EditorLoadJobState()
        self.midi_preview_jobs = MidiPreviewJobState()

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

    def close(self) -> None:
        self.close_attempts += 1
        if gui_shutdown.request_window_close(self):
            self.closed = True


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


def test_flush_messages_allows_deferred_close_after_worker_completion() -> None:
    window = _FlushWindow()
    window.close_after_worker = True
    window.messages.put(("ENABLE_PROCESS", 7, "cancelled"))

    gui_processing.flush_messages(window)

    assert window.close_attempts == 1
    assert window.closed is True
    assert window.close_after_worker is False
    assert window.worker_jobs.active_token is None
