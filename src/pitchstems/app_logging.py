from __future__ import annotations

import faulthandler
import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path


_ORIGINAL_EXCEPTHOOK = sys.excepthook
_ORIGINAL_THREADING_EXCEPTHOOK = threading.excepthook
_FAULT_STREAM = None


def logs_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if root:
        return Path(root) / "PitchStems" / "logs"
    return Path.home() / ".cache" / "pitchstems" / "logs"


def setup_app_logging() -> Path:
    directory = logs_dir()
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory / "pitchstems.log"
    fault_path = directory / "pitchstems-faults.log"

    logger = logging.getLogger("pitchstems")
    logger.setLevel(logging.INFO)
    for existing_handler in list(logger.handlers):
        existing_handler.close()
        logger.removeHandler(existing_handler)
    handler = RotatingFileHandler(
        log_path,
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(threadName)s] %(message)s")
    )
    logger.addHandler(handler)
    logger.info("Starting PitchStems")

    global _FAULT_STREAM
    if _FAULT_STREAM is not None:
        _FAULT_STREAM.close()
    _FAULT_STREAM = fault_path.open("a", encoding="utf-8")
    faulthandler.enable(file=_FAULT_STREAM, all_threads=True)

    def log_exception(exc_type, exc_value, exc_traceback) -> None:
        logger.critical(
            "Uncaught exception",
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        _ORIGINAL_EXCEPTHOOK(exc_type, exc_value, exc_traceback)

    def log_thread_exception(args: threading.ExceptHookArgs) -> None:
        logger.critical(
            "Uncaught thread exception in %s",
            args.thread.name if args.thread else "unknown thread",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )
        _ORIGINAL_THREADING_EXCEPTHOOK(args)

    sys.excepthook = log_exception
    threading.excepthook = log_thread_exception
    return log_path


def app_logger() -> logging.Logger:
    return logging.getLogger("pitchstems")
