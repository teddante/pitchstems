from __future__ import annotations

import queue
from pathlib import Path

import pitchstems.gui_processing as gui_processing
import pitchstems.gui_shutdown as gui_shutdown
from pitchstems.gui_jobs import EditorLoadJobState, MidiPreviewJobState, WorkerJobState
from pitchstems.pipeline import PipelineCancelledError, PipelineResult
from pitchstems.separation import SeparationOptions, StemResult
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


class _Checked:
    def __init__(self, checked: bool) -> None:
        self._checked = checked

    def isChecked(self) -> bool:
        return self._checked


class _Text:
    def __init__(self, text: str) -> None:
        self._text = text

    def text(self) -> str:
        return self._text


class _CaptureThread:
    def __init__(self, target, args, daemon) -> None:
        self.target = target
        self.args = args
        self.daemon = daemon
        self.started = False

    def start(self) -> None:
        self.started = True


class _CaptureProcess:
    def __init__(self) -> None:
        self.started = False
        self.terminated = False
        self.exitcode = None

    def start(self) -> None:
        self.started = True

    def is_alive(self) -> bool:
        return self.started and not self.terminated

    def join(self, timeout=0) -> None:
        if self.terminated:
            self.exitcode = -15

    def terminate(self) -> None:
        self.terminated = True


class _CaptureProcessWorker:
    def __init__(self, target, args) -> None:
        self.target = target
        self.args = args
        self.process = _CaptureProcess()
        self.terminated = False

    def is_alive(self) -> bool:
        return self.process.is_alive()

    def drain_messages(self) -> list[object]:
        return []

    def terminate(self, timeout_seconds: float = 2.0) -> bool:
        self.terminated = True
        self.process.terminate()
        self.process.join(timeout=timeout_seconds)
        return True


class _StartProcessingWindow:
    def __init__(self, input_path: Path, output_root: Path) -> None:
        self.worker = None
        self.worker_jobs = WorkerJobState()
        self.drop_zone = type("DropZone", (), {"path": input_path})()
        self.output_dir = _Text(str(output_root))
        self.generate_midi = _Checked(True)
        self.current_result = None
        self.current_stems: list[StemResult] = []
        self.current_input_stem = None
        self.processing_states: list[bool] = []
        self.activities: list[str] = []
        self.logs: list[str] = []

    def selected_midi_stems(self) -> set[str]:
        return {"bass"}

    def selected_separation_options(self) -> SeparationOptions:
        return SeparationOptions()

    def selected_midi_options(self) -> MidiOptions:
        return MidiOptions()

    def set_processing_state(self, busy: bool) -> None:
        self.processing_states.append(busy)

    def begin_activity(self, message: str) -> None:
        self.activities.append(message)

    def append_log(self, message: str) -> None:
        self.logs.append(message)


def test_start_full_processing_requests_no_zip_from_gui(monkeypatch, tmp_path: Path) -> None:
    input_path = tmp_path / "song.wav"
    input_path.write_bytes(b"RIFF")
    window = _StartProcessingWindow(input_path, tmp_path / "out")
    process_workers: list[_CaptureProcessWorker] = []

    def capture_process_worker(target, args):
        worker = _CaptureProcessWorker(target, args)
        process_workers.append(worker)
        return worker

    monkeypatch.setattr(gui_processing, "create_process_worker", capture_process_worker)
    monkeypatch.setattr(gui_processing.threading, "Thread", _CaptureThread)

    gui_processing.start_full_processing(window)

    assert isinstance(window.worker, _CaptureThread)
    assert process_workers
    assert process_workers[0].process.started is True
    assert window.worker_jobs.active_process is process_workers[0]
    request = process_workers[0].args[1]
    assert request.create_zip is False
    assert window.worker.started is True


def test_start_midi_processing_requests_no_zip_from_gui(monkeypatch, tmp_path: Path) -> None:
    input_path = tmp_path / "song.wav"
    input_path.write_bytes(b"RIFF")
    window = _StartProcessingWindow(input_path, tmp_path / "out")
    result = PipelineResult(
        project_dir=tmp_path / "song.pitchstems",
        normalized_audio=tmp_path / "song.pitchstems" / "work" / "song.wav",
        stems=[StemResult("bass", tmp_path / "song.pitchstems" / "stems" / "bass.wav")],
        midi_files=[],
        combined_midi=None,
        zip_path=None,
    )
    window.current_result = result
    window.current_stems = result.stems
    window.current_input_stem = "song"
    process_workers: list[_CaptureProcessWorker] = []

    def capture_process_worker(target, args):
        worker = _CaptureProcessWorker(target, args)
        process_workers.append(worker)
        return worker

    monkeypatch.setattr(gui_processing, "create_process_worker", capture_process_worker)
    monkeypatch.setattr(gui_processing.threading, "Thread", _CaptureThread)

    gui_processing.start_midi_processing(window)

    assert isinstance(window.worker, _CaptureThread)
    assert process_workers
    assert process_workers[0].process.started is True
    assert window.worker_jobs.active_process is process_workers[0]
    request = process_workers[0].args[1]
    assert request.create_zip is False
    assert window.worker.started is True


def test_cancel_processing_requests_active_worker_and_updates_activity() -> None:
    window = DummyWindow()
    token = window.worker_jobs.start()

    assert gui_processing.cancel_processing(window) is True
    assert window.worker_jobs.is_cancel_requested(token)
    assert window.activities[-1] == "Cancelling after the current model stage..."
    assert "Cancellation requested." in window.logs[-1]


def test_cancel_processing_terminates_active_process_worker() -> None:
    window = DummyWindow()
    token = window.worker_jobs.start()
    process_worker = _CaptureProcessWorker(None, ())
    process_worker.process.start()
    assert window.worker_jobs.attach_process(token, process_worker)

    assert gui_processing.cancel_processing(window) is True

    assert window.worker_jobs.is_cancel_requested(token)
    assert process_worker.terminated
    assert window.activities[-1] == "Cancelling worker process..."


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
