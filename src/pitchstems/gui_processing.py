from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from pitchstems.pipeline import (
    PipelineCancelledError,
    PipelineResult,
    process_audio_file,
    process_midi_from_stems,
)
from pitchstems.separation import SeparationOptions, StemResult
from pitchstems.transcription import MidiOptions


@dataclass(frozen=True)
class FullRunRequest:
    input_path: Path
    output_root: Path
    separation_options: SeparationOptions
    generate_midi: bool
    midi_options: MidiOptions
    midi_stems: set[str]
    create_zip: bool
    cancelled: Callable[[], bool]


@dataclass(frozen=True)
class MidiRunRequest:
    result: PipelineResult
    input_stem: str
    stems: list[StemResult]
    midi_options: MidiOptions
    midi_stems: set[str]
    create_zip: bool
    cancelled: Callable[[], bool]


def start_full_processing(window) -> None:
    if window.worker and window.worker.is_alive():
        return
    if not window.drop_zone.path:
        window.append_log("Drop an audio file first.")
        return
    token = start_worker_token(window)
    midi_stems = window.selected_midi_stems()
    request = FullRunRequest(
        input_path=window.drop_zone.path,
        output_root=Path(window.output_dir.text()),
        separation_options=window.selected_separation_options(),
        generate_midi=window.generate_midi.isChecked() and bool(midi_stems),
        midi_options=window.selected_midi_options(),
        midi_stems=midi_stems,
        create_zip=window.create_zip.isChecked(),
        cancelled=lambda token=token: not window.is_active_worker_token(token),
    )

    window.set_processing_state(True)
    window.begin_activity("Running separation + MIDI...")
    window.append_log("Starting separation + MIDI pipeline...")
    window.worker = threading.Thread(target=run_full_pipeline, args=(window, token, request), daemon=True)
    window.worker.start()


def start_midi_processing(window) -> None:
    if window.worker and window.worker.is_alive():
        return
    if not window.current_result or not window.current_stems or not window.current_input_stem:
        window.append_log("Run separation first. Then MIDI can be rerun from those stems.")
        return
    token = start_worker_token(window)
    request = MidiRunRequest(
        result=window.current_result,
        input_stem=window.current_input_stem,
        stems=list(window.current_stems),
        midi_options=window.selected_midi_options(),
        midi_stems=window.selected_midi_stems(),
        create_zip=window.create_zip.isChecked(),
        cancelled=lambda token=token: not window.is_active_worker_token(token),
    )

    window.set_processing_state(True)
    window.begin_activity("Rerunning MIDI...")
    window.append_log("Rerunning MIDI from existing stems...")
    window.worker = threading.Thread(target=run_midi_stage, args=(window, token, request), daemon=True)
    window.worker.start()


def start_worker_token(window) -> int:
    window.worker_token += 1
    window.active_worker_token = window.worker_token
    return window.worker_token


def invalidate_worker_token(window) -> None:
    had_active_worker = window.active_worker_token is not None
    window.worker_token += 1
    window.active_worker_token = None
    if had_active_worker:
        window.set_processing_state(False)


def run_full_pipeline(window, token: int, request: FullRunRequest) -> None:
    try:
        window.logger.info("Starting full pipeline for %s", request.input_path)
        result = process_audio_file(
            request.input_path,
            request.output_root,
            separation_options=request.separation_options,
            generate_midi=request.generate_midi,
            midi_policy="all",
            midi_options=request.midi_options,
            midi_stems=request.midi_stems,
            create_zip=request.create_zip,
            log=lambda message: window.messages.put(("WORKER_LOG", token, message)),
            cancelled=request.cancelled,
        )
        window.messages.put(("RESULT", token, result))
        window.messages.put(("WORKER_LOG", token, f"Project ready: {result.project_dir}"))
    except PipelineCancelledError:
        window.logger.info("Processing cancelled")
        window.messages.put(("WORKER_LOG", token, "Processing cancelled."))
    except Exception as exc:
        window.logger.exception("Full pipeline failed")
        window.messages.put(("WORKER_LOG", token, f"Error: {exc}"))
    finally:
        window.messages.put(("ENABLE_PROCESS", token))


def run_midi_stage(window, token: int, request: MidiRunRequest) -> None:
    try:
        window.logger.info("Starting MIDI rerun for %s", request.result.project_dir)
        result = process_midi_from_stems(
            project_dir=request.result.project_dir,
            input_stem=request.input_stem,
            normalized_audio=request.result.normalized_audio,
            stems=request.stems,
            midi_policy="all",
            midi_options=request.midi_options,
            midi_stems=request.midi_stems,
            create_zip=request.create_zip,
            log=lambda message: window.messages.put(("WORKER_LOG", token, message)),
            cancelled=request.cancelled,
        )
        window.messages.put(("RESULT", token, result))
        window.messages.put(("WORKER_LOG", token, f"Updated project MIDI: {result.project_dir}"))
    except PipelineCancelledError:
        window.logger.info("Processing cancelled")
        window.messages.put(("WORKER_LOG", token, "Processing cancelled."))
    except Exception as exc:
        window.logger.exception("MIDI rerun failed")
        window.messages.put(("WORKER_LOG", token, f"Error: {exc}"))
    finally:
        window.messages.put(("ENABLE_PROCESS", token))


def flush_messages(window) -> None:
    while True:
        try:
            message = window.messages.get_nowait()
        except queue.Empty:
            return
        if isinstance(message, tuple) and message[0] == "RESULT":
            _kind, token, result = message
            if window.is_active_worker_token(int(token)):
                window.set_current_result(result)
            else:
                window.logger.info("Ignored stale worker result for %s", result.project_dir)
        elif isinstance(message, tuple) and message[0] == "WORKER_LOG":
            _kind, token, text = message
            if window.is_active_worker_token(int(token)):
                window.append_log(str(text))
                if text and not str(text).startswith("Tracks:"):
                    window.set_activity_message(str(text)[:120])
            else:
                window.logger.info("Ignored stale worker log: %s", text)
        elif isinstance(message, tuple) and message[0] == "EDITOR_LOADED":
            _kind, token, loaded = message
            window.finish_editor_project_load(int(token), loaded)
        elif isinstance(message, tuple) and message[0] == "EDITOR_LOAD_FAILED":
            _kind, token, project_dir, error = message
            window.finish_editor_project_load_failed(int(token), project_dir, error)
        elif isinstance(message, tuple) and message[0] == "MIDI_PREVIEWS":
            _kind, token, project_dir, requested_stems, previews = message
            for stem_name in requested_stems:
                window.clear_midi_preview_worker(project_dir, stem_name, int(token))
            if (
                token == window.midi_preview_token
                and window.current_result is not None
                and window.current_result.project_dir == project_dir
            ):
                window.rendering_midi_previews.difference_update(requested_stems)
                window.attach_midi_preview_players(previews)
            else:
                window.logger.info("Ignored stale MIDI preview render for %s", project_dir)
        elif isinstance(message, tuple) and message[0] == "MIDI_PREVIEW_FAILED":
            _kind, token, project_dir, requested_stems, error = message
            for stem_name in requested_stems:
                window.clear_midi_preview_worker(project_dir, stem_name, int(token))
            if (
                token == window.midi_preview_token
                and window.current_result is not None
                and window.current_result.project_dir == project_dir
            ):
                window.rendering_midi_previews.difference_update(requested_stems)
                window.refresh_timeline_track_summaries()
                window.append_log(error)
                window.end_activity("MIDI preview audio failed")
            else:
                window.logger.info("Ignored stale MIDI preview failure for %s: %s", project_dir, error)
        elif isinstance(message, tuple) and message[0] == "ENABLE_PROCESS":
            _kind, token = message
            if window.is_active_worker_token(int(token)):
                window.active_worker_token = None
                window.set_processing_state(False)
                window.end_activity("Processing complete")
            else:
                window.logger.info("Ignored stale worker completion for token %s", token)
        elif isinstance(message, str) and message.startswith("__OUTPUT_DIR__"):
            window.latest_output_dir = Path(message.removeprefix("__OUTPUT_DIR__"))
            if window.open_when_done.isChecked():
                window.open_latest_output()
        elif isinstance(message, str):
            window.append_log(message)
            if message and not message.startswith("Tracks:"):
                window.set_activity_message(message[:120])
        else:
            window.logger.warning("Ignored unknown worker message: %r", message)
