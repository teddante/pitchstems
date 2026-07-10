from __future__ import annotations

from collections.abc import Callable
from pathlib import Path


def open_folder(path: Path, opener: Callable[[str], object] | None = None) -> Path:
    target = path.expanduser()
    target.mkdir(parents=True, exist_ok=True)
    result = opener(str(target)) if opener is not None else _qt_open_folder(target)
    if result is False:
        raise RuntimeError(f"Could not open folder: {target}")
    return target


def _qt_open_folder(path: Path) -> bool:
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices

    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))
