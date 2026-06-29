import os
from pathlib import Path

import pytest


pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication

from pitchstems.editor_project import ChordRegion, EditorProject, EditorTrack, NoteEvent
from pitchstems.gui_track_controls import TRACK_CONTROL_MIN_HEIGHT
from pitchstems.gui_timeline import TimelineView


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
        chords=[
            ChordRegion(0.0, 1.0, "G", 0.8),
            ChordRegion(1.25, 2.0, "C", 0.8),
            ChordRegion(2.5, 3.25, "D", 0.8),
        ],
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


def test_timeline_load_setup_can_defer_redraws(tmp_path: Path) -> None:
    _app()
    view = TimelineView()
    redraws = []
    view.on_redraw_started = lambda: redraws.append("redraw")
    project = _project(tmp_path)

    view.set_project(project, redraw=False)
    view.set_manual_chords([project.chords[0]], redraw=False)
    view.set_visible_tracks({"piano"}, redraw=False)

    assert redraws == []
    assert view.manual_chords == [project.chords[0]]
    assert view.visible_tracks == {"piano"}

    view.redraw()

    assert redraws == ["redraw"]
    assert set(view.track_geometries) == {"piano"}


def test_timeline_selection_is_clamped_and_cleared(tmp_path: Path) -> None:
    _app()
    view = TimelineView()
    view.set_project(_project(tmp_path))
    chord_events = []
    view.on_chord_selected = chord_events.append

    view._set_selection(-2.0, 20.0)
    view.selected_chord = view.project.chords[0]
    view._chord_drag = {"chord": view.selected_chord}

    assert view.selection_range() == (0.0, 4.0)
    assert view.selection_ranges() == [(0.0, 4.0)]

    view.clear_selection()

    assert view.selection_range() is None
    assert view.selection_ranges() == []
    assert view.selected_chord is None
    assert view._chord_drag is None
    assert chord_events == [None]


def test_timeline_can_track_multiple_selection_ranges(tmp_path: Path) -> None:
    _app()
    view = TimelineView()
    view.set_project(_project(tmp_path))

    view.selection_segments = [(0.0, 1.0)]
    view._set_selection(2.0, 3.0)

    assert view.selection_range() is None
    assert view.selection_ranges() == [(0.0, 1.0), (2.0, 3.0)]


def test_committing_timeline_selection_clears_selected_chord(tmp_path: Path) -> None:
    _app()
    view = TimelineView()
    view.set_project(_project(tmp_path))
    chord_events = []
    view.on_chord_selected = chord_events.append
    view.selected_chord = view.project.chords[0]

    view._set_selection(1.0, 2.0, notify=True)

    assert view.selection_range() == (1.0, 2.0)
    assert view.selected_chord is None
    assert chord_events == [None]


def test_timeline_select_review_chord_clears_range_and_moves_playhead(tmp_path: Path) -> None:
    _app()
    view = TimelineView()
    view.set_project(_project(tmp_path))
    positions = []
    chord_events = []

    def set_position(seconds: float) -> None:
        positions.append(seconds)
        view.set_position(seconds)

    view.on_position_changed = set_position
    view.on_chord_selected = chord_events.append
    view._set_selection(0.25, 0.75, notify=True)

    selected = view.select_review_chord(1)

    assert selected == view.project.chords[0]
    assert view.selected_chord == selected
    assert view.selection_ranges() == []
    assert positions == [0.0]
    assert chord_events == [selected]

    selected = view.select_review_chord(1)

    assert selected == view.project.chords[1]
    assert view.selected_chord == selected
    assert positions[-1] == 1.25


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


def test_timeline_fit_time_range_to_view_frames_review_target(tmp_path: Path) -> None:
    _app()
    view = TimelineView()
    view.resize(900, 420)
    view.set_project(_project(tmp_path))

    assert view.fit_time_range_to_view(1.25, 2.0)

    assert view.pixels_per_second == 420
    assert view.horizontalScrollBar().value() > 0


def test_timeline_fit_time_range_rejects_tiny_targets(tmp_path: Path) -> None:
    _app()
    view = TimelineView()
    view.resize(900, 420)
    view.set_project(_project(tmp_path))

    assert not view.fit_time_range_to_view(1.0, 1.01)


def test_timeline_note_rects_store_note_events(tmp_path: Path) -> None:
    _app()
    view = TimelineView()
    view.resize(900, 420)
    view.set_project(_project(tmp_path))

    note_items = [
        item.data(1)
        for item in view.scene.items()
        if isinstance(item.data(1), NoteEvent)
    ]

    assert {note.pitch for note in note_items} >= {43, 47, 60}


class _TimelineMouseEvent:
    def __init__(self, pos=None) -> None:
        self._pos = pos
        self.accepted = False

    def pos(self):
        return self._pos

    def accept(self) -> None:
        self.accepted = True


class _TimelineItem:
    def __init__(self, note: NoteEvent | None) -> None:
        self.note = note

    def data(self, role: int):
        return self.note if role == 1 else None


def test_timeline_note_preview_callback_uses_clicked_note(tmp_path: Path) -> None:
    _app()
    view = TimelineView()
    project = _project(tmp_path)
    view.set_project(project)
    clicked = []
    view.on_note_clicked = clicked.append
    view.items = lambda _pos: [_TimelineItem(project.notes[0])]

    assert view._preview_note_from_event(_TimelineMouseEvent())
    assert clicked == [project.notes[0]]


def test_timeline_note_preview_checks_items_beneath_top_overlay(tmp_path: Path) -> None:
    _app()
    view = TimelineView()
    project = _project(tmp_path)
    view.set_project(project)
    clicked = []
    view.on_note_clicked = clicked.append
    view.items = lambda _pos: [_TimelineItem(None), _TimelineItem(project.notes[1])]

    assert view._preview_note_from_event(_TimelineMouseEvent())
    assert clicked == [project.notes[1]]


def test_timeline_note_preview_falls_back_to_note_geometry(tmp_path: Path) -> None:
    _app()
    view = TimelineView()
    project = _project(tmp_path)
    view.set_project(project)
    note = project.notes[0]
    y, height, low_pitch, high_pitch = view.track_geometries[note.stem.lower()]
    note_height = view._note_height(height, low_pitch, high_pitch)
    point = QPointF(
        view._x((note.start + note.end) / 2),
        view._pitch_y(note.pitch, y, height, low_pitch, high_pitch, note_height) + note_height / 2,
    )

    assert view._note_from_scene_point(point) == note


def test_timeline_note_preview_does_not_swallow_scrub_click(tmp_path: Path) -> None:
    _app()
    view = TimelineView()
    view.set_project(_project(tmp_path))
    calls = []
    view._start_chord_edit_from_event = lambda _event: False
    view._preview_note_from_event = lambda _event: calls.append("preview") or True
    view._start_selection_from_event = lambda _event: False
    view._scrub_from_event = lambda _event: calls.append("scrub") or True
    event = _TimelineMouseEvent()
    event.button = lambda: Qt.LeftButton

    view.mousePressEvent(event)

    assert calls == ["preview", "scrub"]
    assert event.accepted


def test_tiny_chord_labels_fall_back_to_root_name() -> None:
    _app()
    view = TimelineView()

    assert view._chord_label_for_width("F#m7b5", 10) == "F#"


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
