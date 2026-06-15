from __future__ import annotations

from pathlib import Path

from pitchstems.gui_jobs import EditorLoadJobState, MidiPreviewJobState, WorkerJobState
from pitchstems.gui_processing import cancel_processing
from pitchstems.gui_shutdown import request_window_close


class _Worker:
    def __init__(self, alive: bool) -> None:
        self._alive = alive

    def is_alive(self) -> bool:
        return self._alive


class _Window:
    def __init__(self, alive: bool) -> None:
        self.worker = _Worker(alive)
        self.worker_jobs = WorkerJobState()
        self.worker_jobs.start()
        self.logs: list[str] = []
        self.activities: list[str] = []
        self.close_after_worker = False
        self.editor_load_jobs = EditorLoadJobState()
        self.midi_preview_jobs = MidiPreviewJobState()

    def append_log(self, message: str) -> None:
        self.logs.append(message)

    def set_activity_message(self, message: str) -> None:
        self.activities.append(message)

    def cancel_processing(self) -> bool:
        return cancel_processing(self)


def test_request_window_close_allows_close_when_no_worker_is_alive() -> None:
    window = _Window(alive=False)

    assert request_window_close(window) is True
    assert not window.close_after_worker


def test_request_window_close_cancels_active_worker_and_defers_close() -> None:
    window = _Window(alive=True)

    assert request_window_close(window) is False
    assert window.worker_jobs.is_cancel_requested(1)
    assert window.close_after_worker
    assert window.activities[-1] == "Cancelling after the current model stage..."


def test_request_window_close_allows_close_when_worker_state_is_retired() -> None:
    window = _Window(alive=True)
    window.worker = None

    assert request_window_close(window) is True


def test_request_window_close_invalidates_auxiliary_workers_when_no_processing() -> None:
    window = _Window(alive=False)
    window.editor_load_jobs.worker = object()  # type: ignore[assignment]
    window.midi_preview_jobs.workers[(Path("song.pitchstems"), "vocals")] = (1, object())  # type: ignore[assignment]

    assert request_window_close(window) is True

    assert window.editor_load_jobs.closing
    assert window.midi_preview_jobs.closing
