from __future__ import annotations

import time
from multiprocessing import Queue

from pitchstems.native_jobs import NativeJobMessage, NativeJobProcess


def _sleeping_job(queue: Queue, token: int) -> None:
    queue.put(("started", token))
    time.sleep(30)


def test_native_job_message_serializes_log_event() -> None:
    message = NativeJobMessage(kind="log", token=3, payload={"text": "started"})

    assert message.as_tuple() == ("NATIVE_JOB", "log", 3, {"text": "started"})


def test_native_job_process_can_be_terminated() -> None:
    job = NativeJobProcess.start(token=9, target=_sleeping_job)
    try:
        assert job.queue.get(timeout=5) == ("started", 9)
        assert job.is_alive()
        job.cancel(timeout_seconds=2.0)
        assert not job.is_alive()
    finally:
        job.cancel(timeout_seconds=2.0)
