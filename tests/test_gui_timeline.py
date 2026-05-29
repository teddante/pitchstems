import os
from pathlib import Path

import pytest


pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from pitchstems.editor_project import ChordRegion, EditorProject, EditorTrack, NoteEvent  # noqa: E402
from pitchstems.gui_track_controls import TRACK_CONTROL_MIN_HEIGHT  # noqa: E402
from pitchstems.gui_timeline import TimelineView  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _project(tmp_path: Path) -> EditorProject:
    return EditorProject(
        project_dir=tmp_path,
        source_audio=tmp_path / "song.wav",
        tracks=[
            EditorTrack("bass", tmp_path / "bass.wav"),
            EditorTrack("piano", tmp_path / "piano.wav"),
        ],
        notes=[
            NoteEvent("bass", 0.0, 1.0, 43, 90),
            NoteEvent("bass", 1.2, 2.0, 47, 70),
            NoteEvent("piano", 0.5, 1.5, 60, 80),
        ],
        chords=[ChordRegion(0.0, 1.0, "G", 0.8)],
        duration=4.0,
    )


def test_timeline_indexes_notes_and_filters_visible_tracks(tmp_path: Path) -> None:
    _app()
    view = TimelineView()
    view.resize(900, 420)
    view.set_project(_project(tmp_path))

    assert set(view.notes_by_track) == {"bass", "piano"}
    assert [note.pitch for note in view._visible_notes_for_track("bass", 0.8, 1.3)] == [43, 47]
    assert set(view.track_geometries) == {"bass", "piano"}

    view.set_visible_tracks({"piano"})

    assert set(view.visible_tracks) == {"piano"}
    assert set(view.track_geometries) == {"piano"}


def test_timeline_selection_is_clamped_and_cleared(tmp_path: Path) -> None:
    _app()
    view = TimelineView()
    view.set_project(_project(tmp_path))

    view._set_selection(-2.0, 20.0)

    assert view.selection_range() == (0.0, 4.0)

    view.clear_selection()

    assert view.selection_range() is None


def test_timeline_fit_song_to_view_keeps_zoom_within_supported_bounds(tmp_path: Path) -> None:
    _app()
    view = TimelineView()
    view.resize(900, 420)
    view.set_project(_project(tmp_path))

    view.fit_song_to_view()

    assert 1 <= view.pixels_per_second <= 420
    assert 0.08 <= view.vertical_zoom <= 3.6
    assert min(height for _y, height, _low, _high in view.track_geometries.values()) >= TRACK_CONTROL_MIN_HEIGHT
    assert view.horizontalScrollBar().value() == 0
    assert view.verticalScrollBar().value() == 0
