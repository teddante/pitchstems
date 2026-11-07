import os

import pytest


pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pitchstems.gui_notation_display import NotationDisplayMixin
from pitchstems.gui_window_shell import WindowShellMixin
from pitchstems.main_window import MainWindow


def test_main_window_composes_its_mixins() -> None:
    assert issubclass(MainWindow, WindowShellMixin)
    assert issubclass(MainWindow, NotationDisplayMixin)


@pytest.mark.parametrize(
    "method",
    [
        "build_workspace_shell",
        "create_menus",
        "apply_ui_scale",
        "display_chord",
        "display_note_name",
        "_create_source_controls",
        "_create_processing_controls",
    ],
)
def test_main_window_exposes_split_methods(method: str) -> None:
    assert callable(getattr(MainWindow, method, None))
