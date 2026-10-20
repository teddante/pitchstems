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


def test_setup_app_logging_is_repeatable_without_duplicate_handlers(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    setup_app_logging()
    second_path = setup_app_logging()

    logger = logging.getLogger("pitchstems")
    assert second_path == logs_dir() / "pitchstems.log"
    assert len(logger.handlers) == 1


def test_app_folders_share_one_per_user_root(tmp_path, monkeypatch) -> None:
    from pitchstems.midi_preview import preview_cache_dir
    from pitchstems.model_assets import model_cache_dir

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert logs_dir() == tmp_path / "PitchStems" / "logs"
    assert model_cache_dir() == tmp_path / "PitchStems" / "bs-roformer-models"
    assert preview_cache_dir() == tmp_path / "PitchStems" / "previews"
