from __future__ import annotations

import ctypes
import os
import sys
from importlib import resources
from pathlib import Path

APP_NAME = "PitchStems"
APP_ORGANIZATION = "PitchStems"
WINDOWS_APP_USER_MODEL_ID = "PitchStems.PitchStems"


def app_data_dir() -> Path:
    """Per-user folder for PitchStems logs, model weights, and scratch previews."""
    root = os.environ.get("LOCALAPPDATA")
    if root:
        return Path(root) / APP_NAME
    return Path.home() / ".cache" / "pitchstems"


def app_icon_path() -> Path | None:
    try:
        icon = resources.files("pitchstems.assets").joinpath("pitchstems.ico")
    except ModuleNotFoundError:
        return None
    with resources.as_file(icon) as path:
        return path if path.exists() else None


def apply_windows_app_identity() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_USER_MODEL_ID)
    except Exception:
        return
