from __future__ import annotations

from pitchstems.gui_jobs import thread_is_alive


CANCELLING_AFTER_STAGE_MESSAGE = "Cancelling after the current model stage..."


def request_window_close(window) -> bool:
    if thread_is_alive(getattr(window, "export_worker", None)):
        if window.cancel_processing():
            window.close_after_export = True
            window.append_log("Close requested; cancelling active export first.")
        return False
    worker = getattr(window, "worker", None)
    if worker is None or not worker.is_alive():
        begin_auxiliary_shutdown(window)
        return True
    if window.cancel_processing():
        window.close_after_worker = True
        window.append_log("Close requested; cancelling active processing first.")
    return False


def begin_auxiliary_shutdown(window) -> None:
    window.waveform_token = getattr(window, "waveform_token", 0) + 1
    window.editor_load_jobs.begin_closing()
    window.midi_preview_jobs.begin_closing()
