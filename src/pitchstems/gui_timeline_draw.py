from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush, QFontMetrics, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication

from pitchstems.editor_models import ChordRegion
from pitchstems.gui_theme import TRACK_COLORS
from pitchstems.timeline_chord_geometry import (
    TimelineLayoutGeometry,
    build_timeline_layout,
    compact_chord_label,
    timeline_seconds_for_x,
)
from dataclasses import dataclass
from pitchstems.time_format import format_time


@dataclass(frozen=True)
class TimelineRenderPolicy:
    pixels_per_second: float
    visible_note_count: int

    @property
    def draw_note_labels(self) -> bool:
        return self.pixels_per_second >= 150 and self.visible_note_count <= 900

    @property
    def dense_render(self) -> bool:
        return self.pixels_per_second < 55 or self.visible_note_count > 2400

    @property
    def enable_tooltips(self) -> bool:
        return self.visible_note_count <= 1400 and not self.dense_render

def _track_color(stem_name: str) -> QColor:
    return QColor(TRACK_COLORS.get(stem_name.lower(), "#475569"))


class TimelineDrawingMixin:
    def redraw(self) -> None:
        if self.project is not None and self.on_redraw_started:
            self.on_redraw_started()
        self.setUpdatesEnabled(False)
        try:
            self.scene.clear()
            self.playhead = None
            self.selection_rects = []
            self._drawn_scene_rect = None
            self.track_geometries = {}
            self.sticky_x_items = []
            self.sticky_y_items = []
            self.chord_drag_preview_items = []
            if self.project is None:
                self.scene.addText("Run separation + MIDI to create an editor timeline.").setPos(18, 18)
                self.scene.setSceneRect(0, 0, 760, 320)
                return

            duration = max(self.project.duration, 10.0)
            layout = self._build_layout_geometry(duration)
            self.track_geometries = layout.track_geometries
            width = layout.content_width
            height = layout.content_height
            self.scene.setSceneRect(0, 0, width, height)
            self.scene.addRect(0, 0, width, height, QPen(Qt.NoPen), QBrush(QColor("#f8fafc")))
            visible_rect = self._visible_scene_rect().adjusted(-160, -90, 220, 90)
            self._drawn_scene_rect = visible_rect
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
            display_label = self.chord_label_formatter(chord.label)
            rect.setToolTip(
                f"{display_label}  {source_label}  {format_time(chord.start)} - {format_time(chord.end)}\n"
                f"Ranking score: {chord.confidence:.0%}\n"
                "Drag the middle to move, drag an edge to resize, Delete removes the selected chord."
            )
            label_width = max(8, int(width) - 8)
            shown_label, marker = self._chord_text_for_width(
                display_label,
                label_width,
                is_edited=source_label == "Edited",
            )
            marker_width = QFontMetrics(QApplication.font()).horizontalAdvance(marker) if marker else 0
            if shown_label:
                text = self.scene.addText(shown_label)
                text.setDefaultTextColor(QColor("#4c1d95"))
                text.setPos(x + 5, self.ruler_height + 5)
                text.setData(0, chord)
                text.setToolTip(rect.toolTip())
                text.setZValue(8)
                self._make_sticky_y(text, 34)
            if source_label == "Edited":
                if not marker:
                    continue
                marker_text = self.scene.addText(marker)
                marker_text.setDefaultTextColor(QColor("#1d4ed8"))
                marker_text.setPos(x + max(5, width - marker_width - 5), self.ruler_height + 5)
                marker_text.setData(0, chord)
                marker_text.setToolTip(rect.toolTip())
                marker_text.setZValue(9)
                self._make_sticky_y(marker_text, 34)
    def _chord_label_for_width(self, label: str, label_width: int) -> str:
        if label_width < 10:
            return ""
        metrics = QFontMetrics(QApplication.font())
        compact = compact_chord_label(label)
        if label_width < 24:
            return compact if metrics.horizontalAdvance(compact) <= label_width else ""
        if metrics.horizontalAdvance(label) > label_width and label_width < 42:
            return compact if metrics.horizontalAdvance(compact) <= label_width else ""
        shown = metrics.elidedText(
            label,
            Qt.ElideRight,
            label_width,
        )
        if metrics.horizontalAdvance(shown) <= label_width:
            return shown
        return compact if metrics.horizontalAdvance(compact) <= label_width else ""
    def _chord_text_for_width(
        self,
        label: str,
        label_width: int,
        *,
        is_edited: bool,
    ) -> tuple[str, str]:
        shown_label = self._chord_label_for_width(label, label_width)
        if not is_edited:
            return shown_label, ""
        used_width = QFontMetrics(QApplication.font()).horizontalAdvance(shown_label)
        marker = self._edited_marker_for_width(max(0, label_width - used_width))
        return shown_label, marker
    def _edited_marker_for_width(self, label_width: int) -> str:
        metrics = QFontMetrics(QApplication.font())
        if label_width >= metrics.horizontalAdvance("Edited") + 22:
            return "Edited"
        if label_width >= metrics.horizontalAdvance("E") + 18:
            return "E"
        return ""
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
            geometry = self.track_geometries[track.name.lower()]
            y, height, low_pitch, high_pitch = geometry
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
            note_label = self._note_label_for_width(self.note_name_formatter(note.pitch), int(width) - 6)
            if not note_label:
                return
            label = self.scene.addText(note_label)
            label.setDefaultTextColor(QColor("#0f172a"))
            label.setPos(x + 3, pitch_y - 3)
            label.setData(1, note)
    def _note_label_for_width(self, label: str, label_width: int) -> str:
        if label_width < 10:
            return ""
        metrics = QFontMetrics(QApplication.font())
        if metrics.horizontalAdvance(label) <= label_width:
            return label
        elided = metrics.elidedText(label, Qt.ElideRight, label_width)
        return elided if metrics.horizontalAdvance(elided) <= label_width else ""
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
    def _build_layout_geometry(self, duration: float) -> TimelineLayoutGeometry:
        if self.project is None:
            return TimelineLayoutGeometry(
                label_width=self.label_width,
                ruler_height=self.ruler_height,
                chord_lane_height=self.chord_lane_height,
                content_width=760,
                content_height=320,
                track_geometries={},
            )
        return build_timeline_layout(
            tracks=self.project.tracks,
            visible_tracks=self.visible_tracks,
            pitch_ranges=self.pitch_ranges,
            duration=duration,
            pixels_per_second=self.pixels_per_second,
            label_width=self.label_width,
            ruler_height=self.ruler_height,
            chord_lane_height=self.chord_lane_height,
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
        index = self.notes_by_track.get(track_key)
        if index is None:
            return []
        return index.overlapping(max(0.0, visible_start), visible_end)
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
