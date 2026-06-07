from __future__ import annotations


CANCELLING_AFTER_STAGE_MESSAGE = "Cancelling after the current model stage..."


def request_worker_cancel(window) -> bool:
    if not window.worker_jobs.cancel():
        return False
    window.set_activity_message(CANCELLING_AFTER_STAGE_MESSAGE)
    return True


def request_window_close(window) -> bool:
    worker = getattr(window, "worker", None)
    if worker is None or not worker.is_alive():
        return True
    if request_worker_cancel(window):
        window.close_after_worker = True
        window.append_log("Close requested; cancelling active processing first.")
    return False
