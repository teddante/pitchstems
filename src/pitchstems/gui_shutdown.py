from __future__ import annotations


def request_window_close(window) -> bool:
    worker = getattr(window, "worker", None)
    if worker is None or not worker.is_alive():
        return True
    if window.worker_jobs.cancel():
        window.close_after_worker = True
        window.append_log("Close requested; cancelling active processing first.")
        window.set_activity_message("Cancelling active work before closing...")
    return False
