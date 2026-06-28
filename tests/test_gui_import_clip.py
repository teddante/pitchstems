import os

import pytest


pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from pitchstems.audio_clip import AudioClipRange
from pitchstems.gui_import_clip import (
    ImportClipPicker,
    can_play_import_clip_preview,
    clip_status_text,
    import_preview_range,
)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class _Point:
    def __init__(self, x: float) -> None:
        self._x = x

    def x(self) -> float:
        return self._x


class _MouseEvent:
    def __init__(self, x: float) -> None:
        self._x = x

    def button(self):
        return Qt.LeftButton

    def position(self) -> _Point:
        return _Point(self._x)


def test_import_clip_picker_selects_and_clears_range() -> None:
    _app()
    picker = ImportClipPicker()
    picker.resize(204, 84)
    picker.duration_seconds = 100.0
    picker.peaks = (0.2, 0.8, 0.4)
    picker.setEnabled(True)
    changes = []
    picker.on_range_changed = lambda clip, _duration: changes.append(clip)

    picker.mousePressEvent(_MouseEvent(54))
    picker.mouseMoveEvent(_MouseEvent(154))
    picker.mouseReleaseEvent(_MouseEvent(154))

    selected = picker.selected_clip_range()
    assert selected is not None
    assert selected.start_seconds == pytest.approx(25.5, abs=0.1)
    assert selected.end_seconds == pytest.approx(76.5, abs=0.1)
    assert changes[-1] == selected

    picker.clear_selection()

    assert picker.selected_clip_range() is None
    assert changes[-1] is None


def test_import_clip_status_formats_whole_file_and_clip() -> None:
    assert clip_status_text(None, 65.0) == "Whole file: 01:05.000"
    assert clip_status_text(AudioClipRange(2.0, 5.5), 10.0) == (
        "Clip: 00:02.000 - 00:05.500 (00:03.500)"
    )


def test_import_preview_range_prefers_selection_and_falls_back_to_whole_file() -> None:
    assert import_preview_range(AudioClipRange(2.0, 5.5), 10.0) == (2.0, 5.5)
    assert import_preview_range(None, 10.0) == (0.0, 10.0)
    assert import_preview_range(None, 0.01) is None


def test_can_play_import_clip_preview_requires_path_preview_range_and_idle_worker(tmp_path) -> None:
    audio_path = tmp_path / "song.wav"

    assert can_play_import_clip_preview(audio_path, None, 10.0, None)
    assert not can_play_import_clip_preview(None, None, 10.0, None)
    assert not can_play_import_clip_preview(audio_path, None, 0.01, None)
    assert not can_play_import_clip_preview(audio_path, None, 10.0, 7)
