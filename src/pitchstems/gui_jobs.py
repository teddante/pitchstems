from __future__ import annotations

import multiprocessing
import os
import queue
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProcessWorker:
    process: Any
    messages: Any
    terminated: bool = False
    cleanup_root: Path | None = None
    cleanup_project_dir: Path | None = None
    cleanup_error: str | None = None
    started: bool = True

    def is_alive(self) -> bool:
        return bool(self.process.is_alive())

    def drain_messages(self) -> list[object]:
        drained: list[object] = []
        while True:
            try:
                message = self.messages.get_nowait()
            except (EOFError, OSError, queue.Empty):
                return drained
            if self._remember_internal_message(message):
                continue
            drained.append(message)

    def terminate(self, timeout_seconds: float = 2.0) -> bool:
        self.drain_messages()
        if not self.started:
            return False
        if not self.process.is_alive():
            self.process.join(timeout=0)
            return False
        if not _terminate_windows_process_tree(self.process):
            self.process.terminate()
        self.process.join(timeout=timeout_seconds)
        if self.process.is_alive() and hasattr(self.process, "kill"):
            self.process.kill()
            self.process.join(timeout=timeout_seconds)
        self.terminated = True
        self._cleanup_terminated_project()
        return True

    def start(self) -> None:
        if self.started:
            raise RuntimeError("Worker process has already been started.")
        self.process.start()
        self.started = True

    def _remember_internal_message(self, message: object) -> bool:
        if (
            isinstance(message, tuple)
            and len(message) >= 3
            and message[0] == "PROJECT_DIR"
            and isinstance(message[2], Path)
        ):
            self.cleanup_project_dir = message[2]
            return True
        return False

    def _cleanup_terminated_project(self) -> None:
        if self.cleanup_root is None or self.cleanup_project_dir is None:
            return
        try:
            root = self.cleanup_root.expanduser().resolve()
            target = self.cleanup_project_dir.expanduser().resolve()
            if target == root or target.suffix != ".pitchstems":
                return
            target.relative_to(root)
            if target.exists():
                if target.is_symlink():
                    self.cleanup_error = f"Refused to remove symlink project folder: {target}"
                    return
                shutil.rmtree(target)
        except Exception as exc:
            self.cleanup_error = str(exc)


def thread_is_alive(worker: threading.Thread | None) -> bool:
    return bool(worker is not None and worker.is_alive())


def _terminate_windows_process_tree(process: Any) -> bool:
    process_id = getattr(process, "pid", None)
    if os.name != "nt" or not isinstance(process_id, int):
        return False
    try:
        completed = subprocess.run(
            ["taskkill", "/PID", str(process_id), "/T", "/F"],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def create_process_worker(target: Any, args: tuple[object, ...]) -> ProcessWorker:
    context = multiprocessing.get_context("spawn")
    messages = context.Queue()
    process = context.Process(target=target, args=(*args, messages))
    return ProcessWorker(process=process, messages=messages, started=False)


@dataclass
class WorkerJobState:
    next_token: int = 0
    active_token: int | None = None
    active_process: ProcessWorker | None = None

    def start(self) -> int:
        self.next_token += 1
        self.active_token = self.next_token
        return self.next_token

    def request_active_cancel(self) -> ProcessWorker | None:
        if self.active_token is None:
            return None
        return self.active_process

    def finish(self, token: int) -> None:
        if self.active_token == token:
            self.active_token = None
            self.active_process = None

    def invalidate(self, *, terminate: bool = True) -> bool:
        had_active = self.active_token is not None
        if terminate:
            self._terminate_active_process()
        self.next_token += 1
        self.active_token = None
        self.active_process = None
        return had_active

    def is_active(self, token: int) -> bool:
        return self.active_token == token

    def attach_process(self, token: int, process: ProcessWorker) -> bool:
        if self.active_token != token:
            return False
        self.active_process = process
        return True

    def _terminate_active_process(self) -> None:
        if self.active_process is not None:
            self.active_process.terminate()


@dataclass
class EditorLoadJobState:
    token: int = 0
    activity_tokens: set[int] = field(default_factory=set)
    worker: threading.Thread | None = None
    closing: bool = False

    def next(self) -> int:
        self.token += 1
        return self.token

    def begin_closing(self) -> None:
        self.token += 1
        self.activity_tokens.clear()
        self.worker = None
        self.closing = True


@dataclass
class MidiPreviewJobState:
    token: int = 0
    workers: dict[tuple[Path, str], tuple[int, threading.Thread]] = field(default_factory=dict)
    activity_counts: dict[int, int] = field(default_factory=dict)
    closing: bool = False

    def next(self) -> int:
        self.token += 1
        self.workers.clear()
        return self.token

    def invalidate_all(self) -> None:
        self.token += 1
        self.workers.clear()

    def begin_closing(self) -> None:
        self.invalidate_all()
        self.activity_counts.clear()
        self.closing = True
