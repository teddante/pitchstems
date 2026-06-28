from __future__ import annotations

import queue
from pathlib import Path

import pitchstems.gui_processing as gui_processing
import pitchstems.gui_shutdown as gui_shutdown
from pitchstems.audio_clip import AudioClipRange
from pitchstems.gui_jobs import EditorLoadJobState, MidiPreviewJobState, WorkerJobState
from pitchstems.pipeline_models import PipelineResult, StemResult
from pitchstems.separation import SeparationOptions
from pitchstems.transcription import MidiOptions


class _Logger:
    def __init__(self) -> None:
        self.infos: list[tuple[object, ...]] = []

    def info(self, *_args, **_kwargs) -> None:
        self.infos.append(_args)

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


class _ClipPicker:
    def __init__(self, clip_range=None) -> None:
        self.clip_range = clip_range

    def selected_clip_range(self):
        return self.clip_range


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
        del timeout
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


class _FinishedProcess:
    exitcode = -15

    def join(self, timeout=0) -> None:
        del timeout


class _TerminatedProcessWorker:
    terminated = True
    cleanup_error = "Refused to remove partial project"
    process = _FinishedProcess()

    def is_alive(self) -> bool:
        return False

    def drain_messages(self) -> list[object]:
        return []


class _StartProcessingWindow:
    def __init__(self, input_path: Path, output_root: Path) -> None:
        self.worker = None
        self.worker_jobs = WorkerJobState()
        self.drop_zone = type("DropZone", (), {"path": input_path})()
        self.output_dir = _Text(str(output_root))
        self.import_clip_picker = _ClipPicker()
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
    assert process_workers[0].cleanup_root == tmp_path / "out"
    request = process_workers[0].args[1]
    assert process_workers[0].target is gui_processing.run_full_pipeline_process
    assert request.cleanup_root == tmp_path / "out"
    assert request.create_zip is False
    assert request.midi_policy == "all"
    assert request.source_clip is None
    assert window.worker.started is True


def test_start_full_processing_passes_import_clip_to_worker(monkeypatch, tmp_path: Path) -> None:
    input_path = tmp_path / "song.wav"
    input_path.write_bytes(b"RIFF")
    window = _StartProcessingWindow(input_path, tmp_path / "out")
    window.import_clip_picker = _ClipPicker(AudioClipRange(2.0, 8.0))
    process_workers: list[_CaptureProcessWorker] = []

    def capture_process_worker(target, args):
        worker = _CaptureProcessWorker(target, args)
        process_workers.append(worker)
        return worker

    monkeypatch.setattr(gui_processing, "create_process_worker", capture_process_worker)
    monkeypatch.setattr(gui_processing.threading, "Thread", _CaptureThread)

    gui_processing.start_full_processing(window)

    request = process_workers[0].args[1]
    assert request.source_clip == AudioClipRange(2.0, 8.0)


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
    assert process_workers[0].cleanup_root is None
    request = process_workers[0].args[1]
    assert process_workers[0].target is gui_processing.run_midi_stage_process
    assert request.cleanup_root is None
    assert request.create_zip is False
    assert request.midi_policy == "all"
    assert window.worker.started is True


def test_run_full_pipeline_process_uses_request_midi_policy(monkeypatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []
    result = PipelineResult(
        project_dir=tmp_path / "song.pitchstems",
        normalized_audio=tmp_path / "song.pitchstems" / "work" / "song.wav",
        stems=[],
        midi_files=[],
        combined_midi=None,
        zip_path=None,
    )

    def fake_process_audio_file(*_args, **kwargs):
        calls.append(kwargs)
        return result

    monkeypatch.setattr(gui_processing, "process_audio_file", fake_process_audio_file)
    messages: queue.Queue[object] = queue.Queue()

    gui_processing.run_full_pipeline_process(
        4,
        gui_processing.FullProcessRunRequest(
            input_path=tmp_path / "song.wav",
            output_root=tmp_path / "out",
            separation_options=SeparationOptions(),
            generate_midi=True,
            midi_policy="pitched",
            midi_options=MidiOptions(),
            midi_stems={"bass"},
            create_zip=False,
        ),
        messages,
    )

    assert calls[0]["midi_policy"] == "pitched"
    assert messages.get_nowait() == ("RESULT", 4, result)


def test_run_midi_stage_process_uses_request_midi_policy(monkeypatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []
    result = PipelineResult(
        project_dir=tmp_path / "song.pitchstems",
        normalized_audio=tmp_path / "song.pitchstems" / "work" / "song.wav",
        stems=[StemResult("bass", tmp_path / "song.pitchstems" / "stems" / "bass.wav")],
        midi_files=[],
        combined_midi=None,
        zip_path=None,
    )

    def fake_process_midi_from_stems(**kwargs):
        calls.append(kwargs)
        return result

    monkeypatch.setattr(gui_processing, "process_midi_from_stems", fake_process_midi_from_stems)
    messages: queue.Queue[object] = queue.Queue()

    gui_processing.run_midi_stage_process(
        5,
        gui_processing.MidiProcessRunRequest(
            result=result,
            input_stem="song",
            stems=result.stems,
            midi_policy="pitched",
            midi_options=MidiOptions(),
            midi_stems={"bass"},
            create_zip=False,
        ),
        messages,
    )

    assert calls[0]["midi_policy"] == "pitched"
    assert messages.get_nowait() == ("RESULT", 5, result)


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


def test_supervise_process_job_reports_cancel_cleanup_warning() -> None:
    window = _Window()

    gui_processing.supervise_process_job(window, 3, _TerminatedProcessWorker())

    assert window.messages.get_nowait() == (
        "WORKER_LOG",
        3,
        "Cancelled project cleanup warning: Refused to remove partial project",
    )
    assert window.messages.get_nowait() == ("WORKER_LOG", 3, "Processing cancelled.")
    assert window.messages.get_nowait() == ("ENABLE_PROCESS", 3, "cancelled")


def test_cancel_processing_reports_no_active_worker() -> None:
    window = DummyWindow()

    assert gui_processing.cancel_processing(window) is False
    assert "No active processing job to cancel." in window.logs[-1]


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
        self.midi_preview_jobs.token = 11
        self.current_result = PipelineResult(
            project_dir=Path("song.pitchstems"),
            normalized_audio=Path("song.pitchstems/work/song.wav"),
            stems=[],
            midi_files=[],
            combined_midi=None,
            zip_path=None,
        )
        self.rendering_midi_previews: set[str] = set()
        self.cleared_midi_preview_workers: list[tuple[Path, str, int]] = []
        self.attached_midi_previews: list[dict[str, Path]] = []
        self.timeline_refreshes = 0

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

    def clear_midi_preview_worker(self, project_dir: Path, stem_name: str, token: int) -> None:
        self.cleared_midi_preview_workers.append((project_dir, stem_name, token))

    def attach_midi_preview_players(self, previews: dict[str, Path]) -> None:
        self.attached_midi_previews.append(previews)

    def refresh_timeline_track_summaries(self) -> None:
        self.timeline_refreshes += 1


def test_flush_messages_reports_cancelled_completion_without_success_text() -> None:
    window = _FlushWindow()
    window.messages.put(("WORKER_LOG", 7, "Processing cancelled."))
    window.messages.put(("ENABLE_PROCESS", 7, "cancelled"))

    gui_processing.flush_messages(window)

    assert window.logs == ["Processing cancelled."]
    assert window.processing_states == [False]
    assert window.activity_messages[-1] == "Processing cancelled"
    assert window.worker_jobs.active_token is None


def test_flush_messages_reports_error_completion_without_success_text() -> None:
    window = _FlushWindow()
    window.messages.put(("WORKER_LOG", 7, "Error: boom"))
    window.messages.put(("ENABLE_PROCESS", 7, "error"))

    gui_processing.flush_messages(window)

    assert window.logs == ["Error: boom"]
    assert window.processing_states == [False]
    assert window.activity_messages[-1] == "Processing failed"
    assert window.worker_jobs.active_token is None


def test_flush_messages_does_not_show_track_progress_as_activity() -> None:
    window = _FlushWindow()
    window.messages.put(("WORKER_LOG", 7, "Tracks: bass, drums"))
    window.messages.put("Tracks: vocals")

    gui_processing.flush_messages(window)

    assert window.logs == ["Tracks: bass, drums", "Tracks: vocals"]
    assert window.activity_messages == []


def test_flush_messages_allows_deferred_close_after_worker_completion() -> None:
    window = _FlushWindow()
    window.close_after_worker = True
    window.messages.put(("ENABLE_PROCESS", 7, "cancelled"))

    gui_processing.flush_messages(window)

    assert window.close_attempts == 1
    assert window.closed is True
    assert window.close_after_worker is False
    assert window.worker_jobs.active_token is None


def test_finish_worker_completion_ignores_stale_token() -> None:
    window = _FlushWindow()

    gui_processing.finish_worker_completion(window, 42, "success")

    assert window.worker_jobs.active_token == 7
    assert window.processing_states == []
    assert window.activity_messages == []
    assert window.logger.infos == [("Ignored stale worker completion for token %s", 42)]


def test_finish_midi_preview_render_attaches_current_preview() -> None:
    window = _FlushWindow()
    window.rendering_midi_previews.update({"piano", "bass"})
    preview = Path("song.pitchstems/editor/midi-preview/piano_midi_preview.wav")

    gui_processing.finish_midi_preview_render(
        window,
        11,
        Path("song.pitchstems"),
        {"piano"},
        {"piano": preview},
    )

    assert window.cleared_midi_preview_workers == [(Path("song.pitchstems"), "piano", 11)]
    assert window.rendering_midi_previews == {"bass"}
    assert window.attached_midi_previews == [{"piano": preview}]
    assert window.logger.infos == []


def test_finish_midi_preview_render_ignores_stale_preview() -> None:
    window = _FlushWindow()
    window.rendering_midi_previews.add("piano")

    gui_processing.finish_midi_preview_render(
        window,
        10,
        Path("song.pitchstems"),
        {"piano"},
        {"piano": Path("stale.wav")},
    )

    assert window.cleared_midi_preview_workers == [(Path("song.pitchstems"), "piano", 10)]
    assert window.rendering_midi_previews == {"piano"}
    assert window.attached_midi_previews == []
    assert window.logger.infos == [("Ignored stale MIDI preview render for %s", Path("song.pitchstems"))]


def test_finish_midi_preview_failure_reports_current_error() -> None:
    window = _FlushWindow()
    window.rendering_midi_previews.update({"piano", "bass"})

    gui_processing.finish_midi_preview_failure(
        window,
        11,
        Path("song.pitchstems"),
        {"piano"},
        "preview failed",
    )

    assert window.cleared_midi_preview_workers == [(Path("song.pitchstems"), "piano", 11)]
    assert window.rendering_midi_previews == {"bass"}
    assert window.timeline_refreshes == 1
    assert window.logs == ["preview failed"]
    assert window.activity_messages[-1] == "MIDI preview audio failed"
