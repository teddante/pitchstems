from __future__ import annotations

import json
import os
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any


@contextmanager
def atomic_replace(path: Path) -> Iterator[Path]:
    """Yield a sibling temporary path that replaces ``path`` when the block succeeds."""
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        yield temporary
        _replace_with_retry(temporary, path)
    finally:
        with suppress(OSError):
            temporary.unlink(missing_ok=True)


def _replace_with_retry(source: Path, target: Path, attempts: int = 10) -> None:
    # On Windows, os.replace fails while another process briefly has the target
    # open (a reader, antivirus, or indexer), so retry for a short moment.
    for attempt in range(attempts):
        try:
            source.replace(target)
            return
        except PermissionError:
            if sys.platform != "win32" or attempt == attempts - 1:
                raise
            time.sleep(0.05)


def write_json_atomic(path: Path, data: Any, *, indent: int | None = 2, fsync: bool = False) -> None:
    with atomic_replace(path) as temporary, temporary.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=indent, sort_keys=True)
        if indent is not None:
            handle.write("\n")
        if fsync:
            handle.flush()
            os.fsync(handle.fileno())
