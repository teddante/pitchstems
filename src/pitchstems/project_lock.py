from __future__ import annotations

import os
import importlib
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


@contextmanager
def project_mutation_lock(project_dir: Path) -> Iterator[None]:
    """Hold a process-scoped OS lock while mutating an existing project."""
    project_dir = project_dir.expanduser().resolve()
    project_dir.mkdir(parents=True, exist_ok=True)
    lock_path = project_dir / ".pitchstems.lock"
    with lock_path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            _lock_file(handle.fileno())
        except OSError as exc:
            raise RuntimeError(f"PitchStems project is already being modified: {project_dir}") from exc
        try:
            yield
        finally:
            _unlock_file(handle.fileno())


def _lock_file(file_descriptor: int) -> None:
    if os.name == "nt":
        msvcrt = importlib.import_module("msvcrt")
        msvcrt.locking(file_descriptor, msvcrt.LK_NBLCK, 1)
        return

    import fcntl

    fcntl.flock(file_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file(file_descriptor: int) -> None:
    if os.name == "nt":
        msvcrt = importlib.import_module("msvcrt")
        os.lseek(file_descriptor, 0, os.SEEK_SET)
        msvcrt.locking(file_descriptor, msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(file_descriptor, fcntl.LOCK_UN)
