from __future__ import annotations

import queue
from pathlib import Path

import pitchstems.gui_jobs as gui_jobs
from pitchstems.gui_jobs import EditorLoadJobState, MidiPreviewJobState, ProcessWorker, WorkerJobState


class _FakeProcess:
    def __init__(self, alive: bool = True) -> None:
        self.alive = alive
        self.terminated = False
        self.killed = False
        self.join_timeouts: list[float | int] = []

    def is_alive(self) -> bool:
        return self.alive

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True
        self.alive = False

    def join(self, timeout=0) -> None:
        self.join_timeouts.append(timeout)


def test_process_worker_reports_alive_and_drains_messages() -> None:
    messages: queue.Queue[object] = queue.Queue()
    messages.put(("WORKER_LOG", 1, "hello"))
    messages.put(("ENABLE_PROCESS", 1, "success"))
    worker = ProcessWorker(_FakeProcess(alive=True), messages)

    assert worker.is_alive()
    assert worker.drain_messages() == [
        ("WORKER_LOG", 1, "hello"),
        ("ENABLE_PROCESS", 1, "success"),
    ]


def test_process_worker_remembers_internal_project_dir_message(tmp_path: Path) -> None:
    messages: queue.Queue[object] = queue.Queue()
    project_dir = tmp_path / "song.pitchstems"
    messages.put(("PROJECT_DIR", 1, project_dir))
    messages.put(("WORKER_LOG", 1, "hello"))
    worker = ProcessWorker(_FakeProcess(alive=True), messages)

    assert worker.drain_messages() == [("WORKER_LOG", 1, "hello")]
    assert worker.cleanup_project_dir == project_dir


def test_process_worker_terminate_joins_completed_process() -> None:
    process = _FakeProcess(alive=False)
    worker = ProcessWorker(process, queue.Queue())

    assert worker.terminate() is False
    assert process.join_timeouts == [0]
    assert not worker.terminated


def test_process_worker_terminate_removes_safe_new_project_dir(tmp_path: Path) -> None:
    process = _FakeProcess(alive=True)
    project_dir = tmp_path / "song.pitchstems"
    project_dir.mkdir()
    (project_dir / "partial.txt").write_text("partial", encoding="utf-8")
    worker = ProcessWorker(
        process,
        queue.Queue(),
        cleanup_root=tmp_path,
        cleanup_project_dir=project_dir,
    )

    assert worker.terminate(timeout_seconds=0.25) is True

    assert not project_dir.exists()
    assert worker.cleanup_error is None


def test_process_worker_terminate_refuses_cleanup_outside_root(tmp_path: Path) -> None:
    process = _FakeProcess(alive=True)
    outside = tmp_path.parent / f"{tmp_path.name}-outside.pitchstems"
    outside.mkdir()
    try:
        worker = ProcessWorker(
            process,
            queue.Queue(),
            cleanup_root=tmp_path,
            cleanup_project_dir=outside,
        )

        assert worker.terminate(timeout_seconds=0.25) is True

        assert outside.exists()
    finally:
        outside.rmdir()


def test_process_worker_terminate_kills_stubborn_process() -> None:
    process = _FakeProcess(alive=True)
    worker = ProcessWorker(process, queue.Queue())

    assert worker.terminate(timeout_seconds=0.25) is True

    assert process.terminated
    assert process.killed
    assert process.join_timeouts == [0.25, 0.25]
    assert worker.terminated


def test_create_process_worker_uses_spawn_context(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []

    class _Context:
        def Queue(self):  # noqa: N802 - mirrors multiprocessing API
            return "messages"

        def Process(self, target, args):  # noqa: N802 - mirrors multiprocessing API
            calls.append((target, args))
            return _FakeProcess()

    monkeypatch.setattr(gui_jobs.multiprocessing, "get_context", lambda _method: _Context())

    worker = gui_jobs.create_process_worker("target", (1, "request"))

    assert calls == [("target", (1, "request", "messages"))]
    assert worker.messages == "messages"


def test_worker_job_state_starts_cancels_and_rejects_stale_tokens() -> None:
    state = WorkerJobState()

    first = state.start()
    assert state.is_active(first)

    assert state.cancel()
    assert state.is_active(first)
    assert state.is_cancel_requested(first)
    assert state.invalidate()
    assert not state.is_active(first)
    assert not state.is_cancel_requested(first)

    second = state.start()
    assert second != first
    assert state.is_active(second)


def test_worker_job_state_reports_no_active_cancel() -> None:
    state = WorkerJobState()

    assert not state.cancel()
    assert state.active_token is None


def test_worker_job_state_tracks_cancel_request_without_clearing_active_token() -> None:
    state = WorkerJobState()
    token = state.start()

    assert state.request_cancel(token) is True
    assert state.active_token == token
    assert state.is_cancel_requested(token)

    state.finish(token)

    assert state.active_token is None
    assert not state.is_cancel_requested(token)


def test_worker_job_state_cancels_attached_process() -> None:
    state = WorkerJobState()
    token = state.start()
    worker = ProcessWorker(_FakeProcess(alive=True), queue.Queue())

    assert state.attach_process(token, worker)
    assert state.cancel()

    assert state.is_cancel_requested(token)
    assert worker.terminated


def test_worker_job_state_rejects_stale_process_and_clears_active_process() -> None:
    state = WorkerJobState()
    token = state.start()
    worker = ProcessWorker(_FakeProcess(alive=True), queue.Queue())

    assert not state.attach_process(token + 1, worker)
    assert state.attach_process(token, worker)
    state.finish(token)

    assert state.active_process is None


def test_worker_job_state_invalidate_terminates_active_process() -> None:
    state = WorkerJobState()
    token = state.start()
    worker = ProcessWorker(_FakeProcess(alive=True), queue.Queue())
    assert state.attach_process(token, worker)

    assert state.invalidate()

    assert worker.terminated
    assert state.active_process is None


def test_editor_load_job_state_tracks_activity_tokens() -> None:
    state = EditorLoadJobState()

    token = state.next()
    state.activity_tokens.add(token)

    assert token in state.activity_tokens


def test_midi_preview_job_state_next_clears_workers(tmp_path) -> None:
    state = MidiPreviewJobState()
    state.workers[(tmp_path, "bass")] = (state.token, None)  # type: ignore[arg-type]

    state.next()

    assert state.workers == {}


def test_editor_load_state_invalidates_and_marks_closing() -> None:
    state = EditorLoadJobState()
    first = state.next()
    state.worker = object()  # type: ignore[assignment]

    state.begin_closing()

    assert state.closing
    assert state.token > first
    assert state.worker is None


def test_midi_preview_state_invalidates_project_workers() -> None:
    state = MidiPreviewJobState()
    state.token = 4
    state.workers[(Path("song.pitchstems"), "vocals")] = (4, object())  # type: ignore[assignment]

    state.invalidate_all()

    assert state.token == 5
    assert state.workers == {}
