from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from pitchstems.app_identity import (
    APP_NAME,
    APP_ORGANIZATION,
    apply_windows_app_identity,
    app_icon_path,
)
from pitchstems.app_logging import app_logger, setup_app_logging
from pitchstems.gui_theme import pitchstems_stylesheet

if TYPE_CHECKING:
    from logging import Logger

    from PySide6.QtWidgets import QApplication, QMainWindow


def main() -> int:
    log_path = setup_app_logging()
    logger = app_logger()
    try:
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("PySide6 is not installed. Install with `pip install -e .[gui]`.")
        return 1

    from pitchstems.main_window import MainWindow

    apply_windows_app_identity()
    app = QApplication([])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORGANIZATION)
    icon_path = app_icon_path()
    if icon_path is not None:
        app.setWindowIcon(QIcon(str(icon_path)))
    app.setStyleSheet(pitchstems_stylesheet())
    window = MainWindow(log_path, logger)
    window.show()
    smoke_mode = os.environ.get("PITCHSTEMS_GUI_SMOKE")
    if smoke_mode in {"startup", "project", "real-audio"}:
        _schedule_gui_smoke(app, window, smoke_mode, logger, log_path)
    return app.exec()


def _schedule_gui_smoke(
    app: QApplication,
    window: QMainWindow,
    smoke_mode: str,
    logger: Logger,
    log_path: Path,
) -> None:
    from PySide6.QtCore import QTimer

    from pitchstems.gui_smoke import (
        capture_visual_audit,
        run_project_smoke,
        run_real_audio_project_smoke,
        run_startup_smoke,
    )

    # The timeout can fire inside processEvents() while the smoke is still
    # running; remember it so the final exit code cannot mask it.
    smoke_timed_out = False
    smoke_timeout_ms = 120_000 if smoke_mode == "real-audio" else 10_000

    def time_out_smoke() -> None:
        nonlocal smoke_timed_out
        smoke_timed_out = True
        print(f"GUI smoke timed out after {smoke_timeout_ms // 1000}s.", file=sys.stderr)
        app.exit(2)

    def run_smoke_and_exit() -> None:
        try:
            run_startup_smoke(window)
            if smoke_mode == "project":
                run_project_smoke(window)
            if smoke_mode == "real-audio":
                manifest = os.environ.get("PITCHSTEMS_REAL_AUDIO_SMOKE_MANIFEST")
                if not manifest:
                    raise RuntimeError("PITCHSTEMS_REAL_AUDIO_SMOKE_MANIFEST is required.")
                run_real_audio_project_smoke(window, Path(manifest))
            visual_audit_dir = os.environ.get("PITCHSTEMS_VISUAL_AUDIT_DIR")
            if visual_audit_dir:
                capture_visual_audit(window, Path(visual_audit_dir))
        except Exception as exc:
            logger.exception("GUI startup smoke failed")
            print(f"{exc} (details: {log_path})", file=sys.stderr)
            app.exit(2 if smoke_timed_out else 1)
            return
        app.exit(2 if smoke_timed_out else 0)

    QTimer.singleShot(0, run_smoke_and_exit)
    QTimer.singleShot(smoke_timeout_ms, time_out_smoke)


if __name__ == "__main__":
    raise SystemExit(main())
