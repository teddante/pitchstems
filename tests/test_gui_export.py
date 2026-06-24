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


def test_export_dialog_bulk_selection_controls(tmp_path: Path) -> None:
    _app()
    items = [
        ExportItem("Project manifest", "Project", tmp_path / "pitchstems.project.json", Path("pitchstems.project.json")),
        ExportItem("Stem", "Stems", tmp_path / "stem.wav", Path("stems/stem.wav")),
        ExportItem("Source audio", "Source Audio", tmp_path / "song.mp3", Path("audio/song.mp3"), default_selected=False),
    ]
    dialog = ExportSelectedFilesDialog(None, items, tmp_path / "export")

    assert [item.label for item in dialog.selected_items()] == ["Project manifest", "Stem"]
    assert dialog._selection_summary.text() == "2 of 3 files selected"

    dialog.select_all_items()

    assert [item.label for item in dialog.selected_items()] == ["Project manifest", "Source audio", "Stem"]
    assert dialog._selection_summary.text() == "3 of 3 files selected"

    dialog.clear_selected_items()

    assert dialog.selected_items() == []
    assert dialog._selection_summary.text() == "0 of 3 files selected"

    dialog.select_default_items()

    assert [item.label for item in dialog.selected_items()] == ["Project manifest", "Stem"]
    assert dialog._selection_summary.text() == "2 of 3 files selected"


def test_export_dialog_category_selection_controls(tmp_path: Path) -> None:
    _app()
    items = [
        ExportItem("Project manifest", "Project", tmp_path / "pitchstems.project.json", Path("pitchstems.project.json")),
        ExportItem("Bass", "Stems", tmp_path / "bass.wav", Path("stems/bass.wav")),
        ExportItem("Drums", "Stems", tmp_path / "drums.wav", Path("stems/drums.wav")),
        ExportItem("Bass MIDI", "MIDI", tmp_path / "bass.mid", Path("midi/bass.mid")),
    ]
    dialog = ExportSelectedFilesDialog(None, items, tmp_path / "export")

    dialog.clear_category_items("Stems")

    assert [item.label for item in dialog.selected_items()] == ["Project manifest", "Bass MIDI"]
    assert dialog._selection_summary.text() == "2 of 4 files selected"

    dialog.clear_selected_items()
    dialog.select_category_items("Stems")

    assert [item.label for item in dialog.selected_items()] == ["Bass", "Drums"]
    assert dialog._selection_summary.text() == "2 of 4 files selected"

    dialog.select_category_items("Missing")

    assert [item.label for item in dialog.selected_items()] == ["Bass", "Drums"]
