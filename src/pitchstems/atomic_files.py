from __future__ import annotations

import json
import os
import threading
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
        temporary.replace(path)
    finally:
        with suppress(OSError):
            temporary.unlink(missing_ok=True)


def write_json_atomic(path: Path, data: Any, *, indent: int | None = 2, fsync: bool = False) -> None:
    with atomic_replace(path) as temporary, temporary.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=indent, sort_keys=True)
        if indent is not None:
            handle.write("\n")
        if fsync:
            handle.flush()
            os.fsync(handle.fileno())
