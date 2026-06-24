from pathlib import Path

import pytest


pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from pitchstems.export_files import ExportItem  # noqa: E402
from pitchstems.gui_export import ExportSelectedFilesDialog  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_export_dialog_respects_default_selected_items(tmp_path: Path) -> None:
    _app()
    manifest = tmp_path / "pitchstems.project.json"
    source = tmp_path / "audio" / "song.mp3"
    items = [
        ExportItem("Project manifest", "Project", manifest, Path("pitchstems.project.json")),
        ExportItem("Source audio", "Source Audio", source, Path("audio/song.mp3"), default_selected=False),
    ]

    dialog = ExportSelectedFilesDialog(None, items, tmp_path / "export")

    assert [item.label for item in dialog.selected_items()] == ["Project manifest"]
