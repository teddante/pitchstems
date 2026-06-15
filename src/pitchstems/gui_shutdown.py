from __future__ import annotations


CANCELLING_AFTER_STAGE_MESSAGE = "Cancelling after the current model stage..."


def request_window_close(window) -> bool:
    worker = getattr(window, "worker", None)
    if worker is None or not worker.is_alive():
        begin_auxiliary_shutdown(window)
        return True
    if window.cancel_processing():
        window.close_after_worker = True
        window.append_log("Close requested; cancelling active processing first.")
    return False


def begin_auxiliary_shutdown(window) -> None:
    window.editor_load_jobs.begin_closing()
    window.midi_preview_jobs.begin_closing()
