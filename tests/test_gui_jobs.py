from __future__ import annotations

from pitchstems.gui_jobs import EditorLoadJobState, MidiPreviewJobState, WorkerJobState


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
