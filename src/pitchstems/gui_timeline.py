from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Iterator
from contextlib import contextmanager

from PySide6.QtCore import QPointF, QTimer, Qt
from PySide6.QtGui import QColor, QBrush, QFontMetrics, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView

from pitchstems.editor_chord_navigation import review_navigation_chord
from pitchstems.editor_project import ChordRegion, EditorProject, NoteEvent, midi_note_name
from pitchstems.gui_theme import TRACK_COLORS
from pitchstems.gui_track_controls import TRACK_CONTROL_MIN_HEIGHT
from pitchstems.timeline_chord_geometry import (
    build_track_geometries,
    chord_drag_mode,
    compact_chord_label,
    dragged_chord_region,
    neighbour_chords,
    snap_seconds_to_timeline_targets,
    timeline_seconds_for_x,
    timeline_x_for_seconds,
)
from pitchstems.timeline_render_policy import TimelineRenderPolicy
from pitchstems.timeline_selection import (
    active_selection_range,
    clamp_selection_bounds,
    commit_selection_range,
    merged_selection_ranges,
)
from pitchstems.time_format import format_time


def _track_color(stem_name: str) -> QColor:
    return QColor(TRACK_COLORS.get(stem_name.lower(), "#475569"))


class TimelineView(QGraphicsView):
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
        self.track_geometries: dict[str, tuple[float, float, int, int]] = {}
        self.notes_by_track: dict[str, list] = {}
        self.note_starts_by_track: dict[str, list[float]] = {}
        self.max_note_duration_by_track: dict[str, float] = {}
        self.pitch_ranges: dict[str, tuple[int, int]] = {}
        self.note_name_formatter = midi_note_name
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
        self.note_starts_by_track = {}
        self.max_note_duration_by_track = {}
        self.pitch_ranges = {}
        if self.project is None:
            return
        for note in self.project.notes:
            self.notes_by_track.setdefault(note.stem.lower(), []).append(note)
        for track_key, notes in self.notes_by_track.items():
            notes.sort(key=lambda note: (note.start, note.end, note.pitch))
            self.note_starts_by_track[track_key] = [note.start for note in notes]
            self.max_note_duration_by_track[track_key] = max(
                (note.duration for note in notes),
                default=0.0,
            )
        for track in self.project.tracks:
            pitches = [note.pitch for note in self.notes_by_track.get(track.name.lower(), [])]
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
        self.redraw()

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
        self.zoom_redraw_timer.stop()
        self.view_redraw_timer.stop()
        self.pending_pixels_per_second = None
        self.pending_vertical_zoom = None
        self.pending_zoom_center_seconds = None
        self.pending_zoom_center_y = None

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
        if end - start < 0.05:
            return False
        self.zoom_redraw_timer.stop()
        self.view_redraw_timer.stop()
        self.pending_pixels_per_second = None
        self.pending_vertical_zoom = None
        self.pending_zoom_center_seconds = None
        self.pending_zoom_center_y = None

        viewport = self.viewport().rect()
        time_width = max(80, viewport.width() - self.label_width - 92)
        range_duration = max(0.05, end - start)
        self.pixels_per_second = max(1, min(420, time_width / range_duration))
        self.redraw()
        target_left = max(0.0, self._x(start) - 24)
        self.horizontalScrollBar().setValue(int(target_left))
        self.update_sticky_labels()
        return True

    def reset_zoom(self) -> None:
        if self.project is None:
            return
        self.zoom_redraw_timer.stop()
        self.pending_pixels_per_second = None
        self.pending_vertical_zoom = None
        self.pending_zoom_center_seconds = None
        self.pending_zoom_center_y = None
        center_seconds = self._view_center_seconds()
        self.pixels_per_second = 92
        self.vertical_zoom = 1.0
        self.redraw()
        self._center_on_seconds(center_seconds)

    def commit_pending_zoom(self) -> None:
        if self.project is None:
            self.pending_pixels_per_second = None
            self.pending_vertical_zoom = None
            self.pending_zoom_center_seconds = None
            self.pending_zoom_center_y = None
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

        self.pending_pixels_per_second = None
        self.pending_vertical_zoom = None
        self.pending_zoom_center_seconds = None
        self.pending_zoom_center_y = None

        self._update_scene_rect_for_current_zoom()
        if has_time_zoom:
            self._center_on_seconds(center_seconds)
        if has_pitch_zoom:
            x = self._x(center_seconds) if has_time_zoom else self.mapToScene(self.viewport().rect().center()).x()
            self.centerOn(x, center_y)
        self.view_redraw_timer.stop()
        self.redraw()
        self.update_sticky_labels()

    def request_view_redraw(self, _value: int | None = None) -> None:
        if self.project is None:
            return
        self.view_redraw_timer.start(35)

    def _update_scene_rect_for_current_zoom(self) -> None:
        if self.project is None:
            return
        duration = max(self.project.duration, 10.0)
        self.track_geometries = self._build_track_geometries()
        width = self.label_width + duration * self.pixels_per_second + 80
        height = self.chord_height + sum(
            geometry[1] for geometry in self.track_geometries.values()
        ) + 34
        self.scene.setSceneRect(0, 0, width, height)

    def set_position(self, seconds: float) -> None:
        if self.project is None:
            self.position = 0.0
            return
        self.position = max(0.0, min(seconds, max(self.project.duration, 0.0)))
        self._move_playhead()

    def redraw(self) -> None:
        if self.project is not None and self.on_redraw_started:
            self.on_redraw_started()
        self.setUpdatesEnabled(False)
        try:
            self.scene.clear()
            self.playhead = None
            self.selection_rects = []
            self.track_geometries = {}
            self.sticky_x_items = []
            self.sticky_y_items = []
            self.chord_drag_preview_items = []
            if self.project is None:
                self.scene.addText("Run separation + MIDI to create an editor timeline.").setPos(18, 18)
                self.scene.setSceneRect(0, 0, 760, 320)
                return

            duration = max(self.project.duration, 10.0)
            self.track_geometries = self._build_track_geometries()
            width = self.label_width + duration * self.pixels_per_second + 80
            height = self.chord_height + sum(
                geometry[1] for geometry in self.track_geometries.values()
            ) + 34
            self.scene.setSceneRect(0, 0, width, height)
            self.scene.addRect(0, 0, width, height, QPen(Qt.NoPen), QBrush(QColor("#f8fafc")))
            visible_rect = self._visible_scene_rect().adjusted(-160, -90, 220, 90)
            visible_start = timeline_seconds_for_x(
                visible_rect.left(),
                label_width=self.label_width,
                pixels_per_second=self.pixels_per_second,
            )
            visible_end = min(
                duration,
                timeline_seconds_for_x(
                    visible_rect.right(),
                    label_width=self.label_width,
                    pixels_per_second=self.pixels_per_second,
                    clamp_minimum=False,
                ),
            )
            if visible_end < visible_start:
                visible_start, visible_end = 0.0, duration
            note_count = self._count_visible_notes(visible_start, visible_end, visible_rect)
            self.last_redraw_stats = (
                f"Timeline redraw: visible notes {note_count}/{len(self.project.notes)}, "
                f"zoom {self.pixels_per_second:.0f}px/s, pitch {self.vertical_zoom:.2f}x"
            )
            self._draw_time_grid(duration, width, height, visible_start, visible_end)
            self._draw_chords(visible_start, visible_end)
            self._draw_tracks(visible_start, visible_end, visible_rect, note_count)
            self._draw_selection(height)
            self._draw_playhead(height)
            self.update_sticky_labels()
        finally:
            self.setUpdatesEnabled(True)
            self.viewport().update()
            if self.project is not None and self.on_redraw_finished:
                self.on_redraw_finished()

    def _draw_time_grid(
        self,
        duration: float,
        width: float,
        height: float,
        visible_start: float,
        visible_end: float,
    ) -> None:
        self.scene.addRect(0, 0, self.label_width, height, QPen(Qt.NoPen), QBrush(QColor("#eef2f7")))
        header = self.scene.addRect(
            0,
            0,
            width,
            self.ruler_height,
            QPen(Qt.NoPen),
            QBrush(QColor("#eef2f7")),
        )
        self._make_sticky_y(header, 26)
        minor_step, major_step = self._time_grid_steps()
        tick = max(0.0, int(visible_start // minor_step) * minor_step)
        end_tick = min(duration + minor_step, visible_end + minor_step)
        while tick <= end_tick:
            x = self._x(tick)
            is_major = self._is_major_tick(tick, major_step)
            color = QColor("#cbd5e1") if is_major else QColor("#e5e7eb")
            self.scene.addLine(x, 0, x, height, QPen(color, 1))
            if is_major:
                text = self.scene.addText(format_time(tick))
                text.setDefaultTextColor(QColor("#475569"))
                text.setPos(x + 4, 3)
                self._make_sticky_y(text, 32)
            tick += minor_step
        self.scene.addLine(self.label_width, 0, self.label_width, height, QPen(QColor("#cbd5e1"), 1))
        ruler_line = self.scene.addLine(0, self.ruler_height, width, self.ruler_height, QPen(QColor("#cbd5e1"), 1))
        self._make_sticky_y(ruler_line, 33)
        header_line = self.scene.addLine(0, self.chord_height, width, self.chord_height, QPen(QColor("#cbd5e1"), 1))
        self._make_sticky_y(header_line, 33)

    def _time_grid_steps(self) -> tuple[float, float]:
        nice_steps = [
            0.25,
            0.5,
            1,
            2,
            5,
            10,
            15,
            30,
            60,
            120,
            300,
            600,
        ]
        target_label_px = 92
        major_step = nice_steps[-1]
        for step in nice_steps:
            if step * self.pixels_per_second >= target_label_px:
                major_step = step
                break
        minor_step = self._minor_step_for_major(major_step)
        return minor_step, major_step

    def _minor_step_for_major(self, major_step: float) -> float:
        if major_step <= 1:
            return major_step / 2
        if major_step in {2, 10, 30, 120, 600}:
            return major_step / 2
        if major_step in {5, 15, 60, 300}:
            return major_step / 5
        return major_step

    def _is_major_tick(self, tick: float, major_step: float) -> bool:
        return abs((tick / major_step) - round(tick / major_step)) < 0.0001

    def _draw_chords(self, visible_start: float, visible_end: float) -> None:
        lane = self.scene.addRect(
            0,
            self.ruler_height,
            self.scene.width(),
            self.chord_lane_height,
            QPen(Qt.NoPen),
            QBrush(QColor("#f3e8ff")),
        )
        self._make_sticky_y(lane, 27)
        label = self.scene.addText("Chords")
        label.setDefaultTextColor(QColor("#334155"))
        label.setPos(12, self.ruler_height + 9)
        self._make_sticky_xy(label, 34)
        for chord in self.project.chords:
            if chord.end < visible_start or chord.start > visible_end:
                continue
            x = self._x(chord.start)
            width = max(18, chord.duration * self.pixels_per_second)
            is_selected = chord == self.selected_chord
            source_label = "Edited" if chord in self.manual_chords else "Auto"
            rect = self.scene.addRect(
                x,
                self.ruler_height + 6,
                width,
                24,
                QPen(QColor("#1d4ed8" if is_selected else "#7c3aed"), 2 if is_selected else 1),
                QBrush(QColor("#dbeafe" if is_selected else "#ede9fe")),
            )
            self._make_sticky_y(rect, 28)
            rect.setData(0, chord)
            rect.setToolTip(
                f"{chord.label}  {source_label}  {format_time(chord.start)} - {format_time(chord.end)}\n"
                f"Ranking score: {chord.confidence:.0%}\n"
                "Drag the middle to move, drag an edge to resize, Delete removes the selected chord."
            )
            label_width = max(8, int(width) - 8)
            timeline_label = f"{chord.label}*" if source_label == "Edited" else chord.label
            shown_label = self._chord_label_for_width(timeline_label, label_width)
            text = self.scene.addText(shown_label)
            text.setDefaultTextColor(QColor("#4c1d95"))
            text.setPos(x + 5, self.ruler_height + 5)
            text.setData(0, chord)
            text.setToolTip(rect.toolTip())
            text.setZValue(8)
            self._make_sticky_y(text, 34)

    def _chord_label_for_width(self, label: str, label_width: int) -> str:
        if label_width < 24:
            return compact_chord_label(label)
        return QFontMetrics(QApplication.font()).elidedText(
            label,
            Qt.ElideRight,
            label_width,
        ) or compact_chord_label(label)

    def _draw_tracks(
        self,
        visible_start: float,
        visible_end: float,
        visible_rect,
        visible_note_count: int,
    ) -> None:
        tracks = self._visible_project_tracks()
        if not tracks:
            text = self.scene.addText("No timeline tracks visible. Tick View for a track to show it here.")
            text.setDefaultTextColor(QColor("#64748b"))
            text.setPos(self.label_width + 18, self.chord_height + 18)
            self._make_sticky_y(text, 12)
            return
        for index, track in enumerate(tracks):
            y, height, low_pitch, high_pitch = self.track_geometries[track.name.lower()]
            fill = QColor("#ffffff") if index % 2 == 0 else QColor("#f1f5f9")
            self.scene.addRect(0, y, self.scene.width(), height, QPen(Qt.NoPen), QBrush(fill))
            self.scene.addLine(
                0,
                y + height,
                self.scene.width(),
                y + height,
                QPen(QColor("#e2e8f0"), 1),
            )
            self._draw_pitch_guides(y, height, low_pitch, high_pitch)

        policy = TimelineRenderPolicy(
            pixels_per_second=self.pixels_per_second,
            visible_note_count=visible_note_count,
        )
        draw_note_labels = policy.draw_note_labels
        dense_render = policy.dense_render
        enable_tooltips = policy.enable_tooltips
        for track in tracks:
            track_key = track.name.lower()
            geometry = self.track_geometries.get(track_key)
            if geometry is None:
                continue
            y, height, low_pitch, high_pitch = geometry
            if y > visible_rect.bottom() or y + height < visible_rect.top():
                continue
            visible_notes = self._visible_notes_for_track(track_key, visible_start, visible_end)
            if dense_render:
                self._draw_dense_notes(
                    visible_notes,
                    y,
                    height,
                    low_pitch,
                    high_pitch,
                    visible_start,
                    visible_end,
                )
            else:
                for note in visible_notes:
                    self._draw_note_event(
                        note,
                        y,
                        height,
                        low_pitch,
                        high_pitch,
                        draw_note_labels,
                        enable_tooltips,
                    )

    def _draw_note_event(
        self,
        note,
        y: float,
        height: float,
        low_pitch: int,
        high_pitch: int,
        draw_note_labels: bool,
        enable_tooltips: bool,
    ) -> None:
        note_height = self._note_height(height, low_pitch, high_pitch)
        pitch_y = self._pitch_y(note.pitch, y, height, low_pitch, high_pitch, note_height)
        x = self._x(note.start)
        width = max(1.0, note.duration * self.pixels_per_second)
        color = _track_color(note.stem)
        velocity = max(1, min(note.velocity, 127))
        velocity_ratio = velocity / 127
        fill_color = QColor(color)
        fill_color.setAlpha(int(70 + velocity_ratio * 185))
        pen_color = QColor(color.darker(150 if velocity_ratio < 0.55 else 125))
        pen_width = 0 if self.pixels_per_second < 80 else 1 if velocity_ratio < 0.72 else 2
        pen = QPen(Qt.NoPen) if pen_width == 0 else QPen(pen_color, pen_width)
        rect = self.scene.addRect(
            x,
            pitch_y,
            width,
            note_height,
            pen,
            QBrush(fill_color),
        )
        if enable_tooltips:
            rect.setToolTip(
                f"{note.stem}: {self.note_name_formatter(note.pitch)}\n"
                f"{format_time(note.start)} - {format_time(note.end)}"
                f"  duration {note.duration:.2f}s\n"
                f"Velocity: {velocity}/127 ({velocity_ratio:.0%})"
            )
        rect.setData(1, note)
        if draw_note_labels and width >= 36:
            label = self.scene.addText(self.note_name_formatter(note.pitch))
            label.setDefaultTextColor(QColor("#0f172a"))
            label.setPos(x + 3, pitch_y - 3)
            label.setData(1, note)

    def _draw_dense_notes(
        self,
        notes,
        y: float,
        height: float,
        low_pitch: int,
        high_pitch: int,
        visible_start: float,
        visible_end: float,
    ) -> None:
        if not notes:
            return
        x_origin = self._x(visible_start)
        image_width = max(1, int((visible_end - visible_start) * self.pixels_per_second) + 8)
        image_height = max(1, int(height) + 1)
        image = QImage(image_width, image_height, QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        note_height = self._note_height(height, low_pitch, high_pitch)
        bin_seconds = max(0.06, 4.0 / self.pixels_per_second)
        bins: dict[tuple[int, int], tuple[int, str]] = {}
        long_notes = []
        first_visible_bin = int(max(0.0, visible_start) / bin_seconds)
        last_visible_bin = int(max(visible_end, visible_start) / bin_seconds) + 1
        try:
            for note in notes:
                start_bin = max(first_visible_bin, int(note.start / bin_seconds))
                end_bin = min(last_visible_bin, max(start_bin, int(note.end / bin_seconds)))
                if end_bin - start_bin > 96:
                    long_notes.append(note)
                    continue
                for time_bin in range(start_bin, end_bin + 1):
                    key = (time_bin, note.pitch)
                    previous_velocity, _previous_stem = bins.get(key, (0, note.stem))
                    if note.velocity > previous_velocity:
                        bins[key] = (note.velocity, note.stem)
            for note in long_notes:
                start = max(note.start, visible_start)
                end = min(note.end, visible_end)
                x = int((start - visible_start) * self.pixels_per_second)
                width = max(2, int((end - start) * self.pixels_per_second))
                pitch_y = int(self._pitch_y(note.pitch, 0, height, low_pitch, high_pitch, note_height))
                color = QColor(_track_color(note.stem))
                color.setAlpha(int(50 + min(1.0, note.velocity / 127) * 145))
                painter.fillRect(x, pitch_y, width, max(1, int(note_height)), color)
            for (time_bin, pitch), (velocity, stem) in bins.items():
                start = max(visible_start, time_bin * bin_seconds)
                x = int((start - visible_start) * self.pixels_per_second)
                width = max(2, int(bin_seconds * self.pixels_per_second))
                pitch_y = int(self._pitch_y(pitch, 0, height, low_pitch, high_pitch, note_height))
                color = QColor(_track_color(stem))
                color.setAlpha(int(55 + min(1.0, velocity / 127) * 150))
                painter.fillRect(x, pitch_y, width, max(1, int(note_height)), color)
        finally:
            painter.end()
        item = self.scene.addPixmap(QPixmap.fromImage(image))
        item.setPos(x_origin, y)

    def _draw_playhead(self, height: float) -> None:
        self.playhead = self.scene.addLine(0, 0, 0, height, QPen(QColor("#ef4444"), 2))
        self._move_playhead()

    def _draw_selection(self, height: float) -> None:
        self.selection_rects = []
        for start, end in self.selection_ranges():
            x = self._x(start)
            width = max(2.0, (end - start) * self.pixels_per_second)
            rect = self.scene.addRect(
                x,
                0,
                width,
                height,
                QPen(QColor("#2563eb"), 1),
                QBrush(QColor(37, 99, 235, 38)),
            )
            rect.setZValue(9)
            self.selection_rects.append(rect)

    def _move_playhead(self) -> None:
        if self.playhead is None:
            return
        x = self._x(self.position)
        line = self.playhead.line()
        line.setLine(x, line.y1(), x, line.y2())
        self.playhead.setLine(line)

    def selection_range(self) -> tuple[float, float] | None:
        ranges = self.selection_ranges()
        if len(ranges) != 1:
            return None
        return ranges[0]

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

    def _build_track_geometries(self) -> dict[str, tuple[float, float, int, int]]:
        if self.project is None:
            return {}
        return build_track_geometries(
            tracks=self.project.tracks,
            visible_tracks=self.visible_tracks,
            pitch_ranges=self.pitch_ranges,
            chord_height=self.chord_height,
            minimum_track_height=self.minimum_track_height,
            vertical_zoom=self.vertical_zoom,
        )

    def _visible_project_tracks(self):
        if self.project is None:
            return []
        return [
            track
            for track in self.project.tracks
            if track.name.lower() in self.visible_tracks
        ]

    def _draw_pitch_guides(
        self,
        y: float,
        height: float,
        low_pitch: int,
        high_pitch: int,
    ) -> None:
        for pitch in range(low_pitch, high_pitch + 1):
            if pitch % 12 != 0:
                continue
            note_height = self._note_height(height, low_pitch, high_pitch)
            pitch_y = self._pitch_y(pitch, y, height, low_pitch, high_pitch, note_height)
            self.scene.addLine(
                self.label_width,
                pitch_y + note_height / 2,
                self.scene.width(),
                pitch_y + note_height / 2,
                QPen(QColor("#e2e8f0"), 1),
            )
            label = self.scene.addText(self.note_name_formatter(pitch))
            label.setDefaultTextColor(QColor("#64748b"))
            label_x = 12
            label.setPos(label_x, pitch_y - 5)
            self._make_sticky(label, label_x)

    def _visible_scene_rect(self):
        return self.mapToScene(self.viewport().rect()).boundingRect()

    def _count_visible_notes(self, visible_start: float, visible_end: float, visible_rect) -> int:
        count = 0
        for track_key in self.notes_by_track:
            if track_key not in self.visible_tracks:
                continue
            geometry = self.track_geometries.get(track_key)
            if geometry is None:
                continue
            y, height, _low_pitch, _high_pitch = geometry
            if y > visible_rect.bottom() or y + height < visible_rect.top():
                continue
            count += len(self._visible_notes_for_track(track_key, visible_start, visible_end))
        return count

    def _visible_notes_for_track(self, track_key: str, visible_start: float, visible_end: float):
        notes = self.notes_by_track.get(track_key, [])
        starts = self.note_starts_by_track.get(track_key, [])
        if not notes or not starts:
            return []
        max_duration = self.max_note_duration_by_track.get(track_key, 0.0)
        start_index = bisect_left(starts, max(0.0, visible_start - max_duration))
        end_index = bisect_right(starts, visible_end)
        return [
            note
            for note in notes[start_index:end_index]
            if note.end >= visible_start and note.start <= visible_end
        ]

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

    def _pitch_y(
        self,
        pitch: int,
        y: float,
        height: float,
        low_pitch: int,
        high_pitch: int,
        note_height: float,
    ) -> float:
        span = max(1, high_pitch - low_pitch)
        drawable = max(1.0, height - 30 - note_height)
        return y + 16 + ((high_pitch - pitch) / span) * drawable

    def _note_height(self, height: float, low_pitch: int, high_pitch: int) -> float:
        span = max(1, high_pitch - low_pitch + 1)
        return max(7.0, min(13.0, (height - 30) / span * 0.82))

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
        edited = self._dragged_chord_from_event(event)
        self._chord_drag = None
        self._clear_chord_drag_preview()
        self.unsetCursor()
        self.selected_chord = edited
        if self.on_chord_edited:
            self.on_chord_edited(original, edited)

    def _draw_chord_drag_preview(self, chord: ChordRegion) -> None:
        if self.project is None:
            return
        self._clear_chord_drag_preview()
        x = self._x(chord.start)
        width = max(18, chord.duration * self.pixels_per_second)
        pen = QPen(QColor("#2563eb"), 2)
        pen.setStyle(Qt.DashLine)
        rect = self.scene.addRect(
            x,
            self.ruler_height + 4,
            width,
            28,
            pen,
            QBrush(QColor(219, 234, 254, 180)),
        )
        self._make_sticky_y(rect, 45)
        shown_label = self._chord_label_for_width(chord.label, max(8, int(width) - 8))
        text = self.scene.addText(shown_label)
        text.setDefaultTextColor(QColor("#1d4ed8"))
        text.setPos(x + 5, self.ruler_height + 4)
        self._make_sticky_y(text, 46)
        self.chord_drag_preview_items = [rect, text]
        self.update_sticky_labels()

    def _clear_chord_drag_preview(self) -> None:
        for item in self.chord_drag_preview_items:
            if item.scene() is self.scene:
                self.scene.removeItem(item)
        self.sticky_y_items = [
            (item, y_offset)
            for item, y_offset in self.sticky_y_items
            if item not in self.chord_drag_preview_items
        ]
        self.chord_drag_preview_items = []

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
