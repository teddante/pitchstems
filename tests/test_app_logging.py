import logging

from pitchstems.app_logging import app_logger, logs_dir, setup_app_logging


def test_setup_app_logging_writes_log_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    log_path = setup_app_logging()
    app_logger().info("test log entry")

    assert log_path == logs_dir() / "pitchstems.log"
    assert log_path.exists()
    assert "test log entry" in log_path.read_text(encoding="utf-8")
    assert logging.getLogger("pitchstems").handlers
