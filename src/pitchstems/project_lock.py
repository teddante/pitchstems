from __future__ import annotations

import importlib
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterator

MUTATION_LOCK_FILENAME = ".pitchstems.lock"
MANIFEST_LOCK_FILENAME = ".pitchstems.manifest.lock"


class ProjectLockTimeoutError(RuntimeError):
    """Raised when a short-lived project lock cannot be acquired in time."""


@contextmanager
def project_mutation_lock(project_dir: Path) -> Iterator[None]:
    """Hold a process-scoped OS lock while mutating an existing project."""
    project_dir = project_dir.expanduser().resolve()
    project_dir.mkdir(parents=True, exist_ok=True)
    with _open_lock_file(project_dir / MUTATION_LOCK_FILENAME) as handle:
        try:
            _lock_file(handle.fileno())
        except OSError as exc:
            raise RuntimeError(f"PitchStems project is already being modified: {project_dir}") from exc
        try:
            yield
        finally:
            _unlock_file(handle.fileno())


@contextmanager
def try_project_mutation_lock(project_dir: Path) -> Iterator[bool]:
    """Yield True while holding the mutation lock, or False when another writer holds it."""
    project_dir = project_dir.expanduser().resolve()
    project_dir.mkdir(parents=True, exist_ok=True)
    with _open_lock_file(project_dir / MUTATION_LOCK_FILENAME) as handle:
        try:
            _lock_file(handle.fileno())
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            _unlock_file(handle.fileno())


@contextmanager
def project_manifest_lock(project_dir: Path, timeout_seconds: float = 10.0) -> Iterator[None]:
    """Serialize manifest read-modify-write cycles across threads and processes.

    Unlike the mutation lock this is held only for the duration of one manifest
    update, so callers wait briefly instead of failing immediately.
    """
    project_dir = project_dir.expanduser().resolve()
    project_dir.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    with _open_lock_file(project_dir / MANIFEST_LOCK_FILENAME) as handle:
        while True:
            try:
                _lock_file(handle.fileno())
                break
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise ProjectLockTimeoutError(
                        f"Timed out waiting to update the project manifest: {project_dir}"
                    ) from exc
                time.sleep(0.02)
        try:
            yield
        finally:
            _unlock_file(handle.fileno())


@contextmanager
def _open_lock_file(lock_path: Path) -> Iterator[BinaryIO]:
    with lock_path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        yield handle


def _lock_file(file_descriptor: int) -> None:
    if sys.platform == "win32":
        msvcrt = importlib.import_module("msvcrt")
        os.lseek(file_descriptor, 0, os.SEEK_SET)
        msvcrt.locking(file_descriptor, msvcrt.LK_NBLCK, 1)
        return

    import fcntl

    fcntl.flock(file_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file(file_descriptor: int) -> None:
    if sys.platform == "win32":
        msvcrt = importlib.import_module("msvcrt")
        os.lseek(file_descriptor, 0, os.SEEK_SET)
        msvcrt.locking(file_descriptor, msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(file_descriptor, fcntl.LOCK_UN)
