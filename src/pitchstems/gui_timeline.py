from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from PySide6.QtCore import QPointF, QTimer, Qt
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView

from pitchstems.editor_models import ChordRegion, NoteEvent
from pitchstems.editor_project import EditorProject
from pitchstems.editor_query import NoteIndex
from pitchstems.notation import midi_note_name
from pitchstems.gui_timeline_draw import TimelineDrawingMixin
from pitchstems.gui_track_controls import TRACK_CONTROL_MIN_HEIGHT
from pitchstems.timeline_chord_geometry import (
    TimelineTrackGeometry,
    chord_drag_mode,
    dragged_chord_region,
    neighbour_chords,
    snap_seconds_to_timeline_targets,
    timeline_seconds_for_x,
    timeline_x_for_seconds,
)
from pitchstems.review_ranges import (
    MIN_RANGE_SECONDS,
    active_selection_range,
    clamp_selection_bounds,
    commit_selection_range,
    merged_selection_ranges,
    review_navigation_chord,
    single_review_range,
)


class TimelineView(TimelineDrawingMixin, QGraphicsView):
    def __init__(self) -> None:
        super().__init__()
        self.project: EditorProject | None = None
        self.position = 0.0
        self.pixels_per_second = 92
        self.vertical_zoom = 1.0
        self.label_width = 72
        self.ruler_height = 28
        self.chord_lane_height = 36
        self.chord_height = self.ruler_height + self.chord_lane_height
        self.minimum_track_height = TRACK_CONTROL_MIN_HEIGHT
        self.visible_tracks: set[str] = set()
        self._drawn_scene_rect = None
        self.track_geometries: dict[str, TimelineTrackGeometry] = {}
        self.notes_by_track: dict[str, NoteIndex] = {}
        self.pitch_ranges: dict[str, tuple[int, int]] = {}
        self.note_name_formatter = midi_note_name
        self.chord_label_formatter = lambda label: label
        self.last_redraw_stats = ""
        self.sticky_x_items = []
        self.sticky_y_items = []
        self.playhead = None
        self.selection_rects = []
        self.selection_segments: list[tuple[float, float]] = []
        self.manual_chords: list[ChordRegion] = []
        self.selection_start: float | None = None
        self.selection_end: float | None = None
        self.selected_chord: ChordRegion | None = None
        self.on_position_changed = None
        self.on_selection_changed = None
        self.on_chord_edited = None
        self.on_chord_deleted = None
        self.on_chord_selected = None
        self.on_note_clicked = None
        self.on_redraw_started = None
        self.on_redraw_finished = None
        self.pending_pixels_per_second: float | None = None
        self.pending_vertical_zoom: float | None = None
        self.pending_zoom_center_seconds: float | None = None
        self.pending_zoom_center_y: float | None = None
        self._chord_drag = None
        self.chord_drag_preview_items = []
        self._selecting = False
        self._selection_additive = False
        self._selection_anchor: float | None = None
        self._panning = False
        self._last_pan_pos = None
        self._redraw_batch_depth = 0
        self._redraw_pending = False
        self.scene = QGraphicsScene(self)
        self.scene.setItemIndexMethod(QGraphicsScene.NoIndex)
        self.setScene(self.scene)
        self.setMinimumHeight(320)
        self.setOptimizationFlag(QGraphicsView.DontSavePainterState, True)
        self.setOptimizationFlag(QGraphicsView.DontAdjustForAntialiasing, True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet("QGraphicsView { border: 1px solid #e2e8f0; background: #ffffff; border-radius: 6px; }")
        self.horizontalScrollBar().valueChanged.connect(self.update_sticky_labels)
        self.verticalScrollBar().valueChanged.connect(self.update_sticky_labels)
        self.horizontalScrollBar().valueChanged.connect(self.request_view_redraw)
        self.verticalScrollBar().valueChanged.connect(self.request_view_redraw)
        self.zoom_redraw_timer = QTimer(self)
        self.zoom_redraw_timer.setSingleShot(True)
        self.zoom_redraw_timer.timeout.connect(self.commit_pending_zoom)
        self.view_redraw_timer = QTimer(self)
        self.view_redraw_timer.setSingleShot(True)
        self.view_redraw_timer.timeout.connect(self.redraw)

    @contextmanager
    def deferred_redraw(self) -> Iterator[None]:
        self._redraw_batch_depth += 1
        succeeded = False
        try:
            yield
            succeeded = True
        finally:
            self._redraw_batch_depth -= 1
            if self._redraw_batch_depth == 0:
                should_redraw = succeeded and self._redraw_pending
                self._redraw_pending = False
                if should_redraw:
                    self.redraw()

    def request_redraw(self) -> None:
        if self._redraw_batch_depth:
            self._redraw_pending = True
            return
        self.redraw()

    def set_project(self, project: EditorProject | None) -> None:
        self.project = project
        self.visible_tracks = {track.name.lower() for track in project.tracks} if project else set()
        self._index_project()
        self.position = 0.0
        self.selection_start = None
        self.selection_end = None
        self.selection_segments = []
        self._selecting = False
        self._selection_additive = False
        self._chord_drag = None
        self.selected_chord = None
        self.request_redraw()

    def set_manual_chords(self, chords: list[ChordRegion]) -> None:
        self.manual_chords = list(chords)
        self.request_redraw()

    def _index_project(self) -> None:
        self.notes_by_track = {}
        self.pitch_ranges = {}
        if self.project is None:
            return
        grouped: dict[str, list[NoteEvent]] = {}
        for note in self.project.notes:
            grouped.setdefault(note.stem.lower(), []).append(note)
        self.notes_by_track = {track_key: NoteIndex(notes) for track_key, notes in grouped.items()}
        for track in self.project.tracks:
            index = self.notes_by_track.get(track.name.lower())
            pitches = [note.pitch for note in index.notes] if index is not None else []
            if pitches:
                self.pitch_ranges[track.name.lower()] = (
                    max(0, min(pitches) - 2),
                    min(127, max(pitches) + 2),
                )

    def set_visible_tracks(self, tracks: set[str]) -> None:
        self.visible_tracks = {track.lower() for track in tracks}
        self.request_redraw()

    def set_note_name_formatter(self, formatter) -> None:
        self.note_name_formatter = formatter
        self.request_redraw()

    def set_chord_label_formatter(self, formatter) -> None:
        self.chord_label_formatter = formatter
        self.request_redraw()

    def replace_project_keeping_view(
        self,
        project: EditorProject,
        visible_tracks: set[str],
        selected_chord: ChordRegion | None,
        manual_chords: list[ChordRegion],
    ) -> None:
        """Swap in a chord-edited project without resetting playhead, zoom, or selection."""
        notes_changed = self.project is None or project.notes is not self.project.notes
        self.project = project
        if notes_changed:
            self._index_project()
        self.visible_tracks = {track.lower() for track in visible_tracks}
        self.position = max(0.0, min(self.position, max(project.duration, 0.0)))
        self.selected_chord = selected_chord
        self.set_manual_chords(manual_chords)

    def zoom_horizontal(self, factor: float) -> None:
        if self.project is None:
            return
        if self.pending_zoom_center_seconds is None:
            self.pending_zoom_center_seconds = self._view_center_seconds()
        base = self.pending_pixels_per_second or self.pixels_per_second
        self.pending_pixels_per_second = max(1, min(420, base * factor))
        self.zoom_redraw_timer.start(65)

    def zoom_vertical(self, factor: float) -> None:
        if self.project is None:
            return
        if self.pending_zoom_center_y is None:
            self.pending_zoom_center_y = self.mapToScene(self.viewport().rect().center()).y()
        base = self.pending_vertical_zoom or self.vertical_zoom
        self.pending_vertical_zoom = max(0.08, min(3.6, base * factor))
        self.zoom_redraw_timer.start(65)

    def fit_song_to_view(self) -> None:
        if self.project is None:
            return
        self._clear_pending_zoom(stop_zoom_timer=True, stop_view_timer=True)

        duration = max(self.project.duration, 1.0)
        viewport = self.viewport().rect()
        time_width = max(80, viewport.width() - self.label_width - 92)
        self.pixels_per_second = max(1, min(420, time_width / duration))

        track_base_height = 0.0
        for track in self._visible_project_tracks():
            pitch_range = self.pitch_ranges.get(track.name.lower())
            if pitch_range:
                low_pitch, high_pitch = pitch_range
                track_base_height += max(132, (high_pitch - low_pitch + 1) * 8 + 34)
            else:
                track_base_height += 132
        target_height = max(120, viewport.height() - 26)
        track_target_height = max(48, target_height - self.chord_height - 34)
        self.vertical_zoom = max(0.08, min(3.6, track_target_height / max(track_base_height, 1.0)))

        self.redraw()
        self.horizontalScrollBar().setValue(0)
        self.verticalScrollBar().setValue(0)
        self.update_sticky_labels()

    def fit_time_range_to_view(self, start: float, end: float) -> bool:
        if self.project is None:
            return False
        duration = max(self.project.duration, 0.0)
        start = max(0.0, min(start, duration))
        end = max(0.0, min(end, duration))
        if end - start < MIN_RANGE_SECONDS:
            return False
        self._clear_pending_zoom(stop_zoom_timer=True, stop_view_timer=True)

        viewport = self.viewport().rect()
        time_width = max(80, viewport.width() - self.label_width - 92)
        range_duration = max(MIN_RANGE_SECONDS, end - start)
        self.pixels_per_second = max(1, min(420, time_width / range_duration))
        self.redraw()
        target_left = max(0.0, self._x(start) - 24)
        self.horizontalScrollBar().setValue(int(target_left))
        self.update_sticky_labels()
        return True

    def reset_zoom(self) -> None:
        if self.project is None:
            return
        self._clear_pending_zoom(stop_zoom_timer=True)
        center_seconds = self._view_center_seconds()
        self.pixels_per_second = 92
        self.vertical_zoom = 1.0
        self.redraw()
        self._center_on_seconds(center_seconds)

    def commit_pending_zoom(self) -> None:
        if self.project is None:
            self._clear_pending_zoom()
            return
        has_time_zoom = self.pending_pixels_per_second is not None
        has_pitch_zoom = self.pending_vertical_zoom is not None
        if not has_time_zoom and not has_pitch_zoom:
            return

        center_seconds = self.pending_zoom_center_seconds or self._view_center_seconds()
        center_y = self.pending_zoom_center_y
        if center_y is None:
            center_y = self.mapToScene(self.viewport().rect().center()).y()
        if self.pending_pixels_per_second is not None:
            self.pixels_per_second = self.pending_pixels_per_second
        if self.pending_vertical_zoom is not None:
            self.vertical_zoom = self.pending_vertical_zoom

        self._clear_pending_zoom()

        self._update_scene_rect_for_current_zoom()
        if has_time_zoom:
            self._center_on_seconds(center_seconds)
        if has_pitch_zoom:
            x = self._x(center_seconds) if has_time_zoom else self.mapToScene(self.viewport().rect().center()).x()
            self.centerOn(x, center_y)
        self.view_redraw_timer.stop()
        self.redraw()
        self.update_sticky_labels()

    def _clear_pending_zoom(
        self,
        *,
        stop_zoom_timer: bool = False,
        stop_view_timer: bool = False,
    ) -> None:
        if stop_zoom_timer:
            self.zoom_redraw_timer.stop()
        if stop_view_timer:
            self.view_redraw_timer.stop()
        self.pending_pixels_per_second = None
        self.pending_vertical_zoom = None
        self.pending_zoom_center_seconds = None
        self.pending_zoom_center_y = None

    def request_view_redraw(self, _value: int | None = None) -> None:
        if self.project is None:
            return
        # Redraw draws a margin around the viewport; skip scrolls that stay inside it.
        if self._drawn_scene_rect is not None and self._drawn_scene_rect.contains(self._visible_scene_rect()):
            return
        self.view_redraw_timer.start(35)

    def _update_scene_rect_for_current_zoom(self) -> None:
        if self.project is None:
            return
        duration = max(self.project.duration, 10.0)
        layout = self._build_layout_geometry(duration)
        self._drawn_scene_rect = None
        self.track_geometries = layout.track_geometries
        self.scene.setSceneRect(0, 0, layout.content_width, layout.content_height)

    def set_position(self, seconds: float) -> None:
        if self.project is None:
            self.position = 0.0
            return
        self.position = max(0.0, min(seconds, max(self.project.duration, 0.0)))
        self._move_playhead()

    def _move_playhead(self) -> None:
        if self.playhead is None:
            return
        x = self._x(self.position)
        line = self.playhead.line()
        line.setLine(x, line.y1(), x, line.y2())
        self.playhead.setLine(line)

    def selection_range(self) -> tuple[float, float] | None:
        return single_review_range(self.selection_ranges())

    def selection_ranges(self) -> list[tuple[float, float]]:
        return merged_selection_ranges(self.selection_segments, self._current_selection_range())

    def _current_selection_range(self) -> tuple[float, float] | None:
        return active_selection_range(self.selection_start, self.selection_end)

    def clear_selection(self) -> None:
        self.selection_start = None
        self.selection_end = None
        self.selection_segments = []
        self._selecting = False
        self._selection_additive = False
        self._selection_anchor = None
        self._clear_selected_chord()
        for rect in self.selection_rects:
            if rect.scene() is self.scene:
                self.scene.removeItem(rect)
        self.selection_rects = []
        if self.on_selection_changed:
            self.on_selection_changed(None)

    def select_review_chord(self, direction: int) -> ChordRegion | None:
        if self.project is None:
            return None
        chord = review_navigation_chord(
            self.project.chords,
            self.selected_chord,
            self.position,
            direction,
        )
        if chord is None:
            return None
        self.selection_start = None
        self.selection_end = None
        self.selection_segments = []
        self._selecting = False
        self._selection_additive = False
        self._selection_anchor = None
        self._chord_drag = None
        self.selected_chord = chord
        if self.on_position_changed:
            self.on_position_changed(chord.start)
        else:
            self.set_position(chord.start)
        if self.on_chord_selected:
            self.on_chord_selected(chord)
        self.redraw()
        return chord

    def _clear_selected_chord(self) -> None:
        had_selected_chord = self.selected_chord is not None
        self.selected_chord = None
        self._chord_drag = None
        if had_selected_chord and self.on_chord_selected:
            self.on_chord_selected(None)

    def _set_selection(self, start: float, end: float, notify: bool = False) -> None:
        if self.project is None:
            return
        self.selection_start, self.selection_end = clamp_selection_bounds(
            start,
            end,
            self.project.duration,
        )
        if notify:
            self._commit_selection()
        height = self.scene.sceneRect().height()
        for rect in self.selection_rects:
            if rect.scene() is self.scene:
                self.scene.removeItem(rect)
        self.selection_rects = []
        self._draw_selection(height)
        if notify and self.on_selection_changed:
            self.on_selection_changed(self.selection_range())

    def _commit_selection(self) -> None:
        selection = self._current_selection_range()
        self.selection_segments = commit_selection_range(
            self.selection_segments,
            selection,
            self._selection_additive,
        )
        if selection is None:
            return
        self.selection_start, self.selection_end = selection
        self._clear_selected_chord()

    def _make_sticky(self, item, x_offset: float) -> None:
        item.setZValue(20)
        self.sticky_x_items.append((item, x_offset))

    def _make_sticky_y(self, item, z_value: int = 30) -> None:
        item.setZValue(z_value)
        self.sticky_y_items.append((item, item.y()))

    def _make_sticky_xy(self, item, z_value: int = 30) -> None:
        item.setZValue(z_value)
        self.sticky_x_items.append((item, item.x()))
        self.sticky_y_items.append((item, item.y()))

    def update_sticky_labels(self, _value: int | None = None) -> None:
        if not self.sticky_x_items and not self.sticky_y_items:
            return
        view_left = self.mapToScene(self.viewport().rect().left(), 0).x()
        view_top = self.mapToScene(0, self.viewport().rect().top()).y()
        x_base = max(0.0, view_left)
        y_base = max(0.0, view_top)
        for item, x_offset in self.sticky_x_items:
            item.setX(x_base + x_offset)
        for item, y_offset in self.sticky_y_items:
            item.setY(y_base + y_offset)

    def mousePressEvent(self, event) -> None:
        if event.button() in {Qt.MiddleButton, Qt.RightButton}:
            self._panning = True
            self._last_pan_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._start_chord_edit_from_event(event):
            event.accept()
            return
        note_previewed = event.button() == Qt.LeftButton and self._preview_note_from_event(event)
        if event.button() == Qt.LeftButton and self._start_selection_from_event(event):
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._scrub_from_event(event):
            event.accept()
            return
        if note_previewed:
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._panning and self._last_pan_pos is not None:
            delta = event.pos() - self._last_pan_pos
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            self._last_pan_pos = event.pos()
            event.accept()
            return
        if self._chord_drag and self._update_chord_edit_from_event(event):
            event.accept()
            return
        if self._selecting and self._update_selection_from_event(event):
            event.accept()
            return
        if event.buttons() & Qt.LeftButton and self._scrub_from_event(event):
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._panning and event.button() in {Qt.MiddleButton, Qt.RightButton}:
            self._panning = False
            self._last_pan_pos = None
            self.unsetCursor()
            event.accept()
            return
        if self._chord_drag and event.button() == Qt.LeftButton:
            self._finish_chord_edit_from_event(event)
            event.accept()
            return
        if self._selecting and event.button() == Qt.LeftButton:
            self._selecting = False
            self._update_selection_from_event(event, notify=True)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in {Qt.Key_Delete, Qt.Key_Backspace} and self.selected_chord is not None:
            chord = self.selected_chord
            self.selected_chord = None
            self._chord_drag = None
            if self.on_chord_deleted:
                self.on_chord_deleted(chord)
            event.accept()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event) -> None:
        modifiers = event.modifiers()
        degrees = event.angleDelta().y() / 120
        horizontal_degrees = event.angleDelta().x() / 120
        if modifiers & Qt.ControlModifier and modifiers & Qt.ShiftModifier:
            if not degrees:
                event.accept()
                return
            self.zoom_vertical(1.14 ** degrees)
            event.accept()
            return
        if modifiers & Qt.ControlModifier:
            if not degrees:
                event.accept()
                return
            self.zoom_horizontal(1.14 ** degrees)
            event.accept()
            return
        if modifiers & Qt.ShiftModifier:
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int((degrees or horizontal_degrees) * 72)
            )
            event.accept()
            return
        super().wheelEvent(event)

    def _scrub_from_event(self, event) -> bool:
        if self.project is None:
            return False
        point = self.mapToScene(event.pos())
        if point.x() < self.label_width:
            return False
        seconds = self._seconds_from_scene_x(point.x())
        if self.on_position_changed:
            self.on_position_changed(seconds)
        else:
            self.set_position(seconds)
        return True

    def _start_chord_edit_from_event(self, event) -> bool:
        if self.project is None:
            return False
        chord = self._chord_at_event(event)
        if chord is None:
            if self._event_in_chord_lane(event):
                self.selected_chord = None
                if self.on_chord_selected:
                    self.on_chord_selected(None)
                self.redraw()
            return False
        seconds = self._seconds_from_event(event)
        mode = chord_drag_mode(
            seconds=seconds,
            chord=chord,
            pixels_per_second=self.pixels_per_second,
        )
        self.selected_chord = chord
        self._chord_drag = {
            "chord": chord,
            "mode": mode,
            "press_seconds": seconds,
            "press_position": event.pos(),
            "preview": chord,
        }
        self.setCursor(Qt.SizeHorCursor if mode != "move" else Qt.ClosedHandCursor)
        if self.on_chord_selected:
            self.on_chord_selected(chord)
        self.redraw()
        return True

    def _preview_note_from_event(self, event) -> bool:
        if self.project is None or self.on_note_clicked is None:
            return False
        note = self._note_from_event(event)
        if note is None:
            return False
        self.on_note_clicked(note)
        return True

    def _note_from_event(self, event) -> NoteEvent | None:
        for item in self.items(event.pos()):
            note = item.data(1)
            if isinstance(note, NoteEvent):
                return note
        point = self.mapToScene(event.pos())
        return self._note_from_scene_point(point)

    def _note_from_scene_point(self, point: QPointF) -> NoteEvent | None:
        if self.project is None or point.x() < self.label_width:
            return None
        seconds = self._seconds_from_scene_x(point.x())
        for track in self._visible_project_tracks():
            geometry = self.track_geometries.get(track.name.lower())
            if geometry is None:
                continue
            y, height, low_pitch, high_pitch = geometry
            if not (y <= point.y() <= y + height):
                continue
            note_height = self._note_height(height, low_pitch, high_pitch)
            slop = max(3.0, note_height * 0.5)
            candidates = []
            for note in self._visible_notes_for_track(track.name.lower(), seconds, seconds):
                if not (note.start <= seconds <= note.end):
                    continue
                pitch_y = self._pitch_y(note.pitch, y, height, low_pitch, high_pitch, note_height)
                center_y = pitch_y + note_height / 2
                distance = abs(point.y() - center_y)
                if distance <= note_height / 2 + slop:
                    candidates.append((distance, -note.velocity, note))
            if candidates:
                candidates.sort()
                return candidates[0][2]
        return None

    def _update_chord_edit_from_event(self, event) -> bool:
        if self.project is None or not self._chord_drag:
            return False
        preview = self._dragged_chord_from_event(event)
        self._chord_drag["preview"] = preview
        self._draw_chord_drag_preview(preview)
        return True

    def _finish_chord_edit_from_event(self, event) -> None:
        if not self._chord_drag:
            return
        original = self._chord_drag["chord"]
        press_position = self._chord_drag.get("press_position")
        edited = self._dragged_chord_from_event(event)
        self._chord_drag = None
        self._clear_chord_drag_preview()
        self.unsetCursor()
        if (
            edited == original
            or (
                press_position is not None
                and (event.pos() - press_position).manhattanLength() < 4
            )
        ):
            self.selected_chord = original
            return
        self.selected_chord = edited
        if self.on_chord_edited:
            self.on_chord_edited(original, edited)

    def _dragged_chord_from_event(self, event) -> ChordRegion:
        original = self._chord_drag["chord"]
        mode = self._chord_drag["mode"]
        seconds = self._seconds_from_event(event)
        duration = max(0.0, self.project.duration if self.project else original.end)
        previous_chord, next_chord = (
            neighbour_chords(self.project.chords, original)
            if self.project is not None
            else (None, None)
        )
        return dragged_chord_region(
            original=original,
            mode=mode,
            press_seconds=self._chord_drag["press_seconds"],
            seconds=seconds,
            duration=duration,
            previous_chord=previous_chord,
            next_chord=next_chord,
            minimum_length=max(0.08, 4 / self.pixels_per_second),
            snap_seconds=lambda value: self._snap_seconds(value, original),
            snap_enabled=not (event.modifiers() & Qt.AltModifier),
        )

    def _snap_seconds(self, seconds: float, ignored_chord: ChordRegion) -> tuple[float, float]:
        if self.project is None:
            return seconds, 0.0
        return snap_seconds_to_timeline_targets(
            seconds=seconds,
            duration=self.project.duration,
            position=self.position,
            selection_start=self.selection_start,
            selection_end=self.selection_end,
            chords=self.project.chords,
            ignored_chord=ignored_chord,
            pixels_per_second=self.pixels_per_second,
        )

    def _chord_at_event(self, event) -> ChordRegion | None:
        if self.project is None:
            return None
        point = self.mapToScene(event.pos())
        if point.x() < self.label_width:
            return None
        if not self._event_in_chord_lane(event):
            return None
        seconds = self._seconds_from_event(event)
        for chord in reversed(self.project.chords):
            edge_slop = max(0.04, 5 / self.pixels_per_second)
            if chord.start - edge_slop <= seconds <= chord.end + edge_slop:
                return chord
        return None

    def _seconds_from_event(self, event) -> float:
        point = self.mapToScene(event.pos())
        return self._seconds_from_scene_x(point.x())

    def _start_selection_from_event(self, event) -> bool:
        if self.project is None:
            return False
        point = self.mapToScene(event.pos())
        if point.x() < self.label_width:
            return False
        if not self._event_in_chord_lane(event) and not (event.modifiers() & Qt.ShiftModifier):
            return False
        seconds = self._seconds_from_scene_x(point.x())
        self._selection_anchor = max(0.0, min(seconds, max(self.project.duration, 0.0)))
        self._selection_additive = bool(event.modifiers() & Qt.ControlModifier)
        if not self._selection_additive:
            self.selection_segments = []
        self._selecting = True
        self._set_selection(self._selection_anchor, self._selection_anchor)
        return True

    def _update_selection_from_event(self, event, notify: bool = False) -> bool:
        if self.project is None or self._selection_anchor is None:
            return False
        point = self.mapToScene(event.pos())
        seconds = self._seconds_from_scene_x(point.x())
        self._set_selection(self._selection_anchor, seconds, notify=notify)
        return True

    def _x(self, seconds: float) -> float:
        return timeline_x_for_seconds(
            seconds,
            label_width=self.label_width,
            pixels_per_second=self.pixels_per_second,
        )

    def _view_center_seconds(self) -> float:
        point = self.mapToScene(self.viewport().rect().center())
        return self._seconds_from_scene_x(point.x())

    def _seconds_from_scene_x(self, x: float, *, clamp_minimum: bool = True) -> float:
        return timeline_seconds_for_x(
            x,
            label_width=self.label_width,
            pixels_per_second=self.pixels_per_second,
            clamp_minimum=clamp_minimum,
        )

    def _center_on_seconds(self, seconds: float) -> None:
        center = self.mapToScene(self.viewport().rect().center())
        self.centerOn(self._x(seconds), center.y())

    def _event_in_chord_lane(self, event) -> bool:
        point_y = self.mapToScene(event.pos()).y()
        viewport_y = event.pos().y()
        return (
            self.ruler_height <= point_y <= self.chord_height
            or self.ruler_height <= viewport_y <= self.chord_height
        )
