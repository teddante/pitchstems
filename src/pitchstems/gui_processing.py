from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from pitchstems.audio_clip import AudioClipRange
from pitchstems.gui_jobs import ProcessWorker, create_process_worker
from pitchstems.pipeline import (
    PipelineCancelledError,
    process_audio_file,
    process_midi_from_stems,
)
from pitchstems.pipeline_models import PipelineResult, StemResult
from pitchstems.separation import SeparationOptions
from pitchstems.gui_shutdown import CANCELLING_AFTER_STAGE_MESSAGE, begin_auxiliary_shutdown
from pitchstems.input_validation import validate_audio_input
from pitchstems.transcription import MidiOptions


@dataclass(frozen=True)
class FullProcessRunRequest:
    input_path: Path
    output_root: Path
    separation_options: SeparationOptions
    generate_midi: bool
    midi_policy: str
    midi_options: MidiOptions
    midi_stems: set[str]
    create_zip: bool
    source_clip: AudioClipRange | None = None

    @property
    def cleanup_root(self) -> Path | None:
        return self.output_root


@dataclass(frozen=True)
class MidiProcessRunRequest:
    result: PipelineResult
    input_stem: str
    stems: list[StemResult]
    midi_policy: str
    midi_options: MidiOptions
    midi_stems: set[str]
    create_zip: bool

    @property
    def cleanup_root(self) -> Path | None:
        return None


WORKER_COMPLETION_MESSAGES = {
    "cancelled": "Processing cancelled",
    "error": "Processing failed",
}


def start_full_processing(window) -> None:
    if window.worker and window.worker.is_alive():
        return
    if not window.drop_zone.path:
        window.append_log("Drop an audio file first.")
        return
    error = validate_audio_input(window.drop_zone.path)
    if error:
        window.append_log(error)
        return
    token = start_worker_token(window)
    midi_stems = window.selected_midi_stems()

    window.set_processing_state(True)
    window.begin_activity("Running separation + MIDI...")
    window.append_log("Starting separation + MIDI pipeline...")
    start_process_job(
        window,
        token,
        target=run_full_pipeline_process,
        process_request=FullProcessRunRequest(
            input_path=window.drop_zone.path,
            output_root=Path(window.output_dir.text()),
            separation_options=window.selected_separation_options(),
            generate_midi=window.generate_midi.isChecked() and bool(midi_stems),
            midi_policy="all",
            midi_options=window.selected_midi_options(),
            midi_stems=midi_stems,
            create_zip=False,
            source_clip=(
                window.import_clip_picker.selected_clip_range()
                if hasattr(window, "import_clip_picker")
                else None
            ),
        ),
    )


def start_midi_processing(window) -> None:
    if window.worker and window.worker.is_alive():
        return
    if not window.current_result or not window.current_stems or not window.current_input_stem:
        window.append_log("Run separation first. Then MIDI can be rerun from those stems.")
        return
    token = start_worker_token(window)

    window.set_processing_state(True)
    window.begin_activity("Rerunning MIDI...")
    window.append_log("Rerunning MIDI from existing stems...")
    start_process_job(
        window,
        token,
        target=run_midi_stage_process,
        process_request=MidiProcessRunRequest(
            result=window.current_result,
            input_stem=window.current_input_stem,
            stems=list(window.current_stems),
            midi_policy="all",
            midi_options=window.selected_midi_options(),
            midi_stems=window.selected_midi_stems(),
            create_zip=False,
        ),
    )


def start_process_job(window, token: int, target, process_request) -> None:
    process_worker = create_process_worker(target, (token, process_request))
    process_worker.cleanup_root = process_request.cleanup_root
    if not window.worker_jobs.attach_process(token, process_worker):
        process_worker.terminate(timeout_seconds=0.5)
        return
    process_worker.process.start()
    window.worker = threading.Thread(
        target=supervise_process_job,
        args=(window, token, process_worker),
        daemon=True,
    )
    window.worker.start()


def supervise_process_job(window, token: int, process_worker: ProcessWorker) -> None:
    while process_worker.is_alive():
        forward_process_messages(window, process_worker)
        time.sleep(0.05)
    process_worker.process.join(timeout=0)
    forward_process_messages(window, process_worker)
    if process_worker.terminated:
        if process_worker.cleanup_error:
            put_worker_log(
                window.messages,
                token,
                f"Cancelled project cleanup warning: {process_worker.cleanup_error}",
            )
        put_worker_log(window.messages, token, "Processing cancelled.")
        put_worker_completion(window.messages, token, "cancelled")
    elif process_worker.process.exitcode == 0:
        put_worker_completion(window.messages, token, "success")
    else:
        put_worker_log(window.messages, token, f"Worker process exited with code {process_worker.process.exitcode}.")
        put_worker_completion(window.messages, token, "error")


def forward_process_messages(window, process_worker: ProcessWorker) -> None:
    for message in process_worker.drain_messages():
        window.messages.put(message)


def start_worker_token(window) -> int:
    return window.worker_jobs.start()


def cancel_processing(window) -> bool:
    if not window.worker_jobs.cancel():
        window.append_log("No active processing job to cancel.")
        return False
    if window.worker_jobs.active_process is not None:
        window.set_activity_message("Cancelling worker process...")
    else:
        window.set_activity_message(CANCELLING_AFTER_STAGE_MESSAGE)
    window.append_log("Cancellation requested.")
    return True


def invalidate_worker_token(window) -> None:
    had_active_worker = window.worker_jobs.invalidate()
    if had_active_worker:
        window.set_processing_state(False)


def run_full_pipeline_process(token: int, request: FullProcessRunRequest, messages) -> None:
    try:
        result = process_audio_file(
            request.input_path,
            request.output_root,
            separation_options=request.separation_options,
            generate_midi=request.generate_midi,
            midi_policy=request.midi_policy,
            midi_options=request.midi_options,
            midi_stems=request.midi_stems,
            create_zip=request.create_zip,
            log=lambda message: put_worker_log(messages, token, message),
            cancelled=None,
            project_created=lambda project_dir: put_project_dir_message(messages, token, project_dir),
            source_clip=request.source_clip,
        )
        put_worker_result(messages, token, result)
        put_worker_log(messages, token, f"Project ready: {result.project_dir}")
    except PipelineCancelledError:
        put_worker_log(messages, token, "Processing cancelled.")
        raise
    except Exception as exc:
        put_worker_log(messages, token, f"Error: {exc}")
        raise


def run_midi_stage_process(token: int, request: MidiProcessRunRequest, messages) -> None:
    try:
        result = process_midi_from_stems(
            project_dir=request.result.project_dir,
            input_stem=request.input_stem,
            normalized_audio=request.result.normalized_audio,
            stems=request.stems,
            source_audio=request.result.source_audio,
            source_clip=request.result.source_clip,
            original_source_audio=request.result.original_source_audio,
            midi_policy=request.midi_policy,
            midi_options=request.midi_options,
            midi_stems=request.midi_stems,
            create_zip=request.create_zip,
            log=lambda message: put_worker_log(messages, token, message),
            cancelled=None,
        )
        put_worker_result(messages, token, result)
        put_worker_log(messages, token, f"Updated project MIDI: {result.project_dir}")
    except PipelineCancelledError:
        put_worker_log(messages, token, "Processing cancelled.")
        raise
    except Exception as exc:
        put_worker_log(messages, token, f"Error: {exc}")
        raise


def put_worker_log(messages, token: int, text: str) -> None:
    messages.put(("WORKER_LOG", token, text))


def put_worker_result(messages, token: int, result: PipelineResult) -> None:
    messages.put(("RESULT", token, result))


def put_project_dir_message(messages, token: int, project_dir: Path) -> None:
    messages.put(("PROJECT_DIR", token, project_dir))


def put_worker_completion(messages, token: int, status: str) -> None:
    messages.put(("ENABLE_PROCESS", token, status))


def worker_message_kind(message: object) -> str | None:
    if not isinstance(message, tuple) or not message:
        return None
    kind = message[0]
    return kind if isinstance(kind, str) else None


def flush_messages(window) -> None:
    while True:
        try:
            message = window.messages.get_nowait()
        except queue.Empty:
            return
        kind = worker_message_kind(message)
        if kind == "RESULT":
            _kind, token, result = message
            if window.is_active_worker_token(int(token)):
                window.set_current_result(result)
            else:
                window.logger.info("Ignored stale worker result for %s", result.project_dir)
        elif kind == "WORKER_LOG":
            _kind, token, text = message
            if window.is_active_worker_token(int(token)):
                append_worker_log_message(window, str(text))
            else:
                window.logger.info("Ignored stale worker log: %s", text)
        elif kind == "EDITOR_LOADED":
            _kind, token, loaded = message
            window.finish_editor_project_load(int(token), loaded)
        elif kind == "EDITOR_LOAD_FAILED":
            _kind, token, project_dir, error = message
            window.finish_editor_project_load_failed(int(token), project_dir, error)
        elif kind == "MIDI_PREVIEWS":
            _kind, token, project_dir, requested_stems, previews = message
            finish_midi_preview_render(window, int(token), project_dir, requested_stems, previews)
        elif kind == "MIDI_PREVIEW_FAILED":
            _kind, token, project_dir, requested_stems, error = message
            finish_midi_preview_failure(window, int(token), project_dir, requested_stems, str(error))
        elif kind == "ENABLE_PROCESS":
            _kind, token, *status_parts = message
            status = str(status_parts[0]) if status_parts else "success"
            finish_worker_completion(window, int(token), status)
        elif isinstance(message, str) and message.startswith("__OUTPUT_DIR__"):
            window.latest_output_dir = Path(message.removeprefix("__OUTPUT_DIR__"))
            if window.open_when_done.isChecked():
                window.open_latest_output()
        elif isinstance(message, str):
            append_worker_log_message(window, message)
        else:
            window.logger.warning("Ignored unknown worker message: %r", message)


def append_worker_log_message(window, message: str) -> None:
    window.append_log(message)
    if message and not message.startswith("Tracks:"):
        window.set_activity_message(message[:120])


def finish_worker_completion(window, token: int, status: str) -> None:
    if not window.is_active_worker_token(token):
        window.logger.info("Ignored stale worker completion for token %s", token)
        return

    window.worker_jobs.finish(token)
    window.set_processing_state(False)
    window.end_activity(WORKER_COMPLETION_MESSAGES.get(status, "Processing complete"))
    close_after_worker_if_requested(window)


def close_after_worker_if_requested(window) -> None:
    if not getattr(window, "close_after_worker", False):
        return

    window.close_after_worker = False
    window.worker = None
    begin_auxiliary_shutdown(window)
    window.close()


def finish_midi_preview_render(
    window,
    token: int,
    project_dir: Path,
    requested_stems: set[str],
    previews: dict[str, Path],
) -> None:
    clear_midi_preview_workers(window, token, project_dir, requested_stems)
    if not is_current_midi_preview_message(window, token, project_dir):
        window.logger.info("Ignored stale MIDI preview render for %s", project_dir)
        return

    clear_rendering_midi_previews(window, requested_stems)
    window.attach_midi_preview_players(previews)


def finish_midi_preview_failure(
    window,
    token: int,
    project_dir: Path,
    requested_stems: set[str],
    error: str,
) -> None:
    clear_midi_preview_workers(window, token, project_dir, requested_stems)
    if not is_current_midi_preview_message(window, token, project_dir):
        window.logger.info("Ignored stale MIDI preview failure for %s: %s", project_dir, error)
        return

    clear_rendering_midi_previews(window, requested_stems)
    window.refresh_timeline_track_summaries()
    window.append_log(error)
    window.end_activity("MIDI preview audio failed")


def clear_rendering_midi_previews(window, stem_names: set[str]) -> None:
    window.rendering_midi_previews.difference_update(stem_names)


def clear_midi_preview_workers(window, token: int, project_dir: Path, stem_names: set[str]) -> None:
    for stem_name in stem_names:
        window.clear_midi_preview_worker(project_dir, stem_name, token)


def is_current_midi_preview_message(window, token: int, project_dir: Path) -> bool:
    return (
        token == window.midi_preview_jobs.token
        and window.current_result is not None
        and window.current_result.project_dir == project_dir
    )
