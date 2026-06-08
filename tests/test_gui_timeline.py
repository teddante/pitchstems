import os
from pathlib import Path

import pytest


pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from pitchstems.editor_project import ChordRegion, EditorProject, EditorTrack, NoteEvent  # noqa: E402
from pitchstems.gui_track_controls import TRACK_CONTROL_MIN_HEIGHT  # noqa: E402
from pitchstems.gui_timeline import TimelineView, compact_chord_label  # noqa: E402
from pitchstems.timeline_chord_geometry import snap_seconds_to_timeline_targets  # noqa: E402


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


def test_tiny_chord_labels_fall_back_to_root_name(tmp_path: Path) -> None:
    _app()
    view = TimelineView()

    assert compact_chord_label("Gmaj9(no3)") == "G"
    assert compact_chord_label("Bb7/D") == "Bb"
    assert view._chord_label_for_width("F#m7b5", 10) == "F#"


def test_timeline_chord_geometry_snaps_to_nearby_targets() -> None:
    ignored = ChordRegion(1.0, 2.0, "C", 0.8)
    nearby = ChordRegion(2.5, 3.25, "G", 0.8)

    snapped, delta = snap_seconds_to_timeline_targets(
        seconds=2.47,
        duration=4.0,
        position=1.5,
        selection_start=0.75,
        selection_end=3.5,
        chords=[ignored, nearby],
        ignored_chord=ignored,
        pixels_per_second=100,
    )

    assert snapped == 2.5
    assert delta == pytest.approx(0.03)
    assert snap_seconds_to_timeline_targets(
        seconds=2.35,
        duration=4.0,
        position=1.5,
        selection_start=0.75,
        selection_end=3.5,
        chords=[ignored, nearby],
        ignored_chord=ignored,
        pixels_per_second=100,
    ) == (2.35, 0.0)


def test_chord_drag_preview_draws_lightweight_feedback(tmp_path: Path) -> None:
    _app()
    view = TimelineView()
    view.resize(900, 180)
    view.set_project(_project(tmp_path))
    view.verticalScrollBar().setValue(view.verticalScrollBar().maximum())

    view._draw_chord_drag_preview(ChordRegion(0.25, 1.25, "Gmaj9(no3)", 0.8))

    assert len(view.chord_drag_preview_items) == 2
    assert all(item.scene() is view.scene for item in view.chord_drag_preview_items)
    assert all(
        any(sticky_item is item for sticky_item, _offset in view.sticky_y_items)
        for item in view.chord_drag_preview_items
    )
    assert view.chord_drag_preview_items[0].y() == pytest.approx(
        max(0.0, view.mapToScene(0, view.viewport().rect().top()).y())
    )

    preview_items = list(view.chord_drag_preview_items)

    view._clear_chord_drag_preview()

    assert all(item.scene() is None for item in preview_items)
    assert view.chord_drag_preview_items == []
    assert not any(sticky_item in preview_items for sticky_item, _offset in view.sticky_y_items)
