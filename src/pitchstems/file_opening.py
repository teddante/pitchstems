from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path


def open_folder(path: Path, opener: Callable[[str], object] | None = None) -> Path:
    target = path.expanduser()
    target.mkdir(parents=True, exist_ok=True)
    startfile = opener or getattr(os, "startfile", None)
    if startfile is None:
        raise RuntimeError("Opening folders is not supported on this platform.")
    startfile(str(target))
    return target
