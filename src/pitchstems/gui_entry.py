from __future__ import annotations

import sys

MISSING_PYSIDE_MESSAGE = "PySide6 is required for the PitchStems GUI. Install with `pip install -e .[gui]`."


def main() -> int:
    try:
        import PySide6  # noqa: F401
    except ImportError:
        _report_startup_error(MISSING_PYSIDE_MESSAGE)
        return 1

    from pitchstems.app import main as run_app

    return run_app()


def _report_startup_error(message: str) -> None:
    if sys.stderr is not None:
        print(message, file=sys.stderr)
    elif sys.platform == "win32":
        # pitchstems-gui.exe runs under pythonw with no console (stderr is None),
        # so a printed message would be invisible.
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, "PitchStems", 0x10)
