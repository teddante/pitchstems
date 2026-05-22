from __future__ import annotations

import os
import queue
import threading
from dataclasses import replace
from pathlib import Path

from pitchstems.acceleration import onnxruntime_status, torch_status
from pitchstems.app_logging import app_logger, logs_dir, setup_app_logging
from pitchstems.editor_project import (
    ChordRegion,
    EditorProject,
    NoteEvent,
    active_notes_at,
    analyze_chord_at,
    analyze_chord_region,
    build_editor_project,
    midi_note_name,
)
from pitchstems.midi_preview import render_midi_preview, render_note_preview
from pitchstems.model_catalog import model_choice
from pitchstems.pipeline import PipelineResult, process_audio_file, process_midi_from_stems
from pitchstems.project_store import (
    PROJECT_FILENAME,
    load_pipeline_result,
    load_project_manifest,
    save_project_manifest,
)
from pitchstems.separation import SeparationOptions, StemResult
from pitchstems.transcription import MidiOptions


def main() -> int:
    log_path = setup_app_logging()
    logger = app_logger()
    try:
        from PySide6.QtCore import QTimer, Qt, QUrl
        from PySide6.QtGui import QAction, QColor, QBrush, QKeySequence, QPen, QShortcut
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        from PySide6.QtWidgets import (
            QApplication,
            QCheckBox,
            QComboBox,
            QDoubleSpinBox,
            QFileDialog,
            QGridLayout,
            QGraphicsScene,
            QGraphicsView,
            QGroupBox,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QListWidget,
            QListWidgetItem,
            QMainWindow,
            QProgressBar,
            QPushButton,
            QSizePolicy,
            QSlider,
            QSpinBox,
            QTabWidget,
            QTextEdit,
            QVBoxLayout,
            QWidget,
        )
    except ImportError:
        print("PySide6 is not installed. Install with `pip install -e .[gui]`.")
        return 1

    class DropZone(QLabel):
        def __init__(self) -> None:
            super().__init__("Drop an audio file here")
            self.setAcceptDrops(True)
            self.setFocusPolicy(Qt.StrongFocus)
            self.setAlignment(Qt.AlignCenter)
            self.setWordWrap(True)
            self.setMinimumHeight(105)
            self.setMaximumHeight(130)
            self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            self.setStyleSheet(
                """
                QLabel {
                    border: 2px dashed #4c7aaf;
                    border-radius: 8px;
                    color: #1f2937;
                    font-size: 19px;
                    background: #f8fafc;
                }
                """
            )
            self.path: Path | None = None
            self.on_path_changed = None

        def set_audio_file(self, path: Path) -> None:
            self.path = path
            self.setText(f"Audio\n{path.name}\n{self._short_path(path.parent)}")
            self.setToolTip(str(path))

        def set_project_file(self, project_dir: Path, source_audio: Path | None) -> None:
            self.path = source_audio
            if source_audio:
                self.setText(
                    f"Project\n{project_dir.name}\nSource: {source_audio.name}"
                )
                self.setToolTip(f"Project: {project_dir}\nSource: {source_audio}")
            else:
                self.setText(f"Project\n{project_dir.name}")
                self.setToolTip(str(project_dir))

        def reset_prompt(self) -> None:
            self.path = None
            self.setText("Drop an audio file here")
            self.setToolTip("")

        def _short_path(self, path: Path, max_length: int = 72) -> str:
            text = str(path)
            if len(text) <= max_length:
                return text
            parts = path.parts
            tail = str(Path(*parts[-2:])) if len(parts) >= 2 else path.name
            return f"...\\{tail}"

        def dragEnterEvent(self, event) -> None:
            if event.mimeData().hasUrls():
                event.acceptProposedAction()

        def dropEvent(self, event) -> None:
            urls = event.mimeData().urls()
            if urls:
                self.set_audio_file(Path(urls[0].toLocalFile()))
                if self.on_path_changed:
                    self.on_path_changed(self.path)

    class NoWheelComboBox(QComboBox):
        def wheelEvent(self, event) -> None:
            event.ignore()

    class NoWheelDoubleSpinBox(QDoubleSpinBox):
        def wheelEvent(self, event) -> None:
            event.ignore()

    class NoWheelSpinBox(QSpinBox):
        def wheelEvent(self, event) -> None:
            event.ignore()

    class TimelineView(QGraphicsView):
        def __init__(self) -> None:
            super().__init__()
            self.project: EditorProject | None = None
            self.position = 0.0
            self.pixels_per_second = 92
            self.vertical_zoom = 1.0
            self.label_width = 128
            self.chord_height = 38
            self.visible_tracks: set[str] = set()
            self.track_geometries: dict[str, tuple[float, float, int, int]] = {}
            self.notes_by_track: dict[str, list] = {}
            self.pitch_ranges: dict[str, tuple[int, int]] = {}
            self.sticky_x_items = []
            self.sticky_y_items = []
            self.playhead = None
            self.selection_rect = None
            self.selection_start: float | None = None
            self.selection_end: float | None = None
            self.selected_chord: ChordRegion | None = None
            self.on_position_changed = None
            self.on_selection_changed = None
            self.on_chord_edited = None
            self.on_chord_deleted = None
            self.on_chord_selected = None
            self.on_redraw_started = None
            self.on_redraw_finished = None
            self.pending_pixels_per_second: float | None = None
            self.pending_vertical_zoom: float | None = None
            self.pending_zoom_center_seconds: float | None = None
            self.pending_zoom_center_y: float | None = None
            self._chord_drag = None
            self._selecting = False
            self._selection_anchor: float | None = None
            self._panning = False
            self._last_pan_pos = None
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
            self.setStyleSheet("QGraphicsView { border: 1px solid #d1d5db; background: #f8fafc; }")
            self.horizontalScrollBar().valueChanged.connect(self.update_sticky_labels)
            self.verticalScrollBar().valueChanged.connect(self.update_sticky_labels)
            self.zoom_redraw_timer = QTimer(self)
            self.zoom_redraw_timer.setSingleShot(True)
            self.zoom_redraw_timer.timeout.connect(self.commit_pending_zoom)

        def set_project(self, project: EditorProject | None) -> None:
            self.project = project
            self.visible_tracks = {track.name.lower() for track in project.tracks} if project else set()
            self._index_project()
            self.position = 0.0
            self.selection_start = None
            self.selection_end = None
            self._selecting = False
            self._chord_drag = None
            self.selected_chord = None
            self.redraw()

        def _index_project(self) -> None:
            self.notes_by_track = {}
            self.pitch_ranges = {}
            if self.project is None:
                return
            for note in self.project.notes:
                self.notes_by_track.setdefault(note.stem.lower(), []).append(note)
            for track in self.project.tracks:
                pitches = [note.pitch for note in self.notes_by_track.get(track.name.lower(), [])]
                if pitches:
                    self.pitch_ranges[track.name.lower()] = (
                        max(0, min(pitches) - 2),
                        min(127, max(pitches) + 2),
                    )

        def set_visible_tracks(self, tracks: set[str]) -> None:
            self.visible_tracks = {track.lower() for track in tracks}
            self.redraw()

        def zoom_horizontal(self, factor: float) -> None:
            if self.project is None:
                return
            if self.pending_zoom_center_seconds is None:
                self.pending_zoom_center_seconds = self._view_center_seconds()
            base = self.pending_pixels_per_second or self.pixels_per_second
            self.pending_pixels_per_second = max(28, min(420, base * factor))
            self.zoom_redraw_timer.start(180)

        def zoom_vertical(self, factor: float) -> None:
            if self.project is None:
                return
            if self.pending_zoom_center_y is None:
                self.pending_zoom_center_y = self.mapToScene(self.viewport().rect().center()).y()
            base = self.pending_vertical_zoom or self.vertical_zoom
            self.pending_vertical_zoom = max(0.45, min(3.6, base * factor))
            self.zoom_redraw_timer.start(180)

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

            self.redraw()
            if has_time_zoom:
                self._center_on_seconds(center_seconds)
            if has_pitch_zoom:
                x = self._x(center_seconds) if has_time_zoom else self.mapToScene(self.viewport().rect().center()).x()
                self.centerOn(x, center_y)
            self.update_sticky_labels()

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
                self.selection_rect = None
                self.track_geometries = {}
                self.sticky_x_items = []
                self.sticky_y_items = []
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
                self._draw_time_grid(duration, width, height)
                self._draw_chords()
                self._draw_tracks()
                self._draw_selection(height)
                self._draw_playhead(height)
                self.update_sticky_labels()
            finally:
                self.setUpdatesEnabled(True)
                self.viewport().update()
                if self.project is not None and self.on_redraw_finished:
                    self.on_redraw_finished()

        def _draw_time_grid(self, duration: float, width: float, height: float) -> None:
            self.scene.addRect(0, 0, self.label_width, height, QPen(Qt.NoPen), QBrush(QColor("#eef2f7")))
            header = self.scene.addRect(
                0,
                0,
                width,
                self.chord_height,
                QPen(Qt.NoPen),
                QBrush(QColor("#eef2f7")),
            )
            self._make_sticky_y(header, 26)
            tick = 0
            tick_step = 1 if self.pixels_per_second >= 48 else 5
            while tick <= int(duration) + 1:
                x = self._x(tick)
                color = QColor("#cbd5e1") if tick % 5 == 0 else QColor("#e5e7eb")
                self.scene.addLine(x, 0, x, height, QPen(color, 1))
                if tick % 5 == 0:
                    text = self.scene.addText(_format_time(tick))
                    text.setDefaultTextColor(QColor("#475569"))
                    text.setPos(x + 4, 3)
                    self._make_sticky_y(text, 32)
                tick += tick_step
            self.scene.addLine(self.label_width, 0, self.label_width, height, QPen(QColor("#cbd5e1"), 1))
            header_line = self.scene.addLine(0, self.chord_height, width, self.chord_height, QPen(QColor("#cbd5e1"), 1))
            self._make_sticky_y(header_line, 33)

        def _draw_chords(self) -> None:
            label = self.scene.addText("Chords")
            label.setDefaultTextColor(QColor("#334155"))
            label.setPos(12, 9)
            self._make_sticky_xy(label, 34)
            for chord in self.project.chords:
                x = self._x(chord.start)
                width = max(18, chord.duration * self.pixels_per_second)
                is_selected = chord == self.selected_chord
                rect = self.scene.addRect(
                    x,
                    7,
                    width,
                    24,
                    QPen(QColor("#1d4ed8" if is_selected else "#7c3aed"), 2 if is_selected else 1),
                    QBrush(QColor("#dbeafe" if is_selected else "#ede9fe")),
                )
                self._make_sticky_y(rect, 28)
                rect.setData(0, chord)
                rect.setToolTip(
                    f"{chord.label}  {_format_time(chord.start)} - {_format_time(chord.end)}\n"
                    f"Confidence: {chord.confidence:.0%}\n"
                    "Drag the middle to move, drag an edge to resize, Delete removes the selected chord."
                )
                if width > 30:
                    text = self.scene.addText(chord.label)
                    text.setDefaultTextColor(QColor("#4c1d95"))
                    text.setPos(x + 5, 6)
                    text.setData(0, chord)
                    self._make_sticky_y(text, 34)

        def _draw_tracks(self) -> None:
            for index, track in enumerate(self.project.tracks):
                y, height, low_pitch, high_pitch = self.track_geometries[track.name.lower()]
                fill = QColor("#ffffff") if index % 2 == 0 else QColor("#f1f5f9")
                self.scene.addRect(0, y, self.scene.width(), height, QPen(Qt.NoPen), QBrush(fill))
                name = self.scene.addText(track.name)
                name.setDefaultTextColor(QColor("#0f172a"))
                name.setPos(12, y + 8)
                self._make_sticky(name, 12)
                range_text = self.scene.addText(f"{midi_note_name(low_pitch)}-{midi_note_name(high_pitch)}")
                range_text.setDefaultTextColor(QColor("#64748b"))
                range_text.setPos(12, y + 30)
                self._make_sticky(range_text, 12)
                self.scene.addLine(
                    0,
                    y + height,
                    self.scene.width(),
                    y + height,
                    QPen(QColor("#e2e8f0"), 1),
                )
                self._draw_pitch_guides(y, height, low_pitch, high_pitch)

            draw_note_labels = self.pixels_per_second >= 150 and len(self.project.notes) <= 900
            for track in self.project.tracks:
                track_key = track.name.lower()
                if track_key not in self.visible_tracks:
                    continue
                geometry = self.track_geometries.get(track_key)
                if geometry is None:
                    continue
                y, height, low_pitch, high_pitch = geometry
                track_notes = self.notes_by_track.get(track_key, [])
                for note in track_notes:
                    self._draw_note_event(note, y, height, low_pitch, high_pitch, draw_note_labels)

        def _draw_note_event(
            self,
            note,
            y: float,
            height: float,
            low_pitch: int,
            high_pitch: int,
            draw_note_labels: bool,
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
            rect.setToolTip(
                f"{note.stem}: {note.name}\n"
                f"{_format_time(note.start)} - {_format_time(note.end)}"
                f"  duration {note.duration:.2f}s\n"
                f"Velocity: {velocity}/127 ({velocity_ratio:.0%})"
            )
            if draw_note_labels and width >= 36:
                label = self.scene.addText(note.name)
                label.setDefaultTextColor(QColor("#0f172a"))
                label.setPos(x + 3, pitch_y - 3)

        def _draw_playhead(self, height: float) -> None:
            self.playhead = self.scene.addLine(0, 0, 0, height, QPen(QColor("#ef4444"), 2))
            self._move_playhead()

        def _draw_selection(self, height: float) -> None:
            self.selection_rect = None
            selection = self.selection_range()
            if selection is None:
                return
            start, end = selection
            x = self._x(start)
            width = max(2.0, (end - start) * self.pixels_per_second)
            self.selection_rect = self.scene.addRect(
                x,
                0,
                width,
                height,
                QPen(QColor("#2563eb"), 1),
                QBrush(QColor(37, 99, 235, 38)),
            )
            self.selection_rect.setZValue(9)

        def _move_playhead(self) -> None:
            if self.playhead is None:
                return
            x = self._x(self.position)
            line = self.playhead.line()
            line.setLine(x, line.y1(), x, line.y2())
            self.playhead.setLine(line)

        def selection_range(self) -> tuple[float, float] | None:
            if self.selection_start is None or self.selection_end is None:
                return None
            start, end = sorted((self.selection_start, self.selection_end))
            if end - start < 0.05:
                return None
            return start, end

        def clear_selection(self) -> None:
            self.selection_start = None
            self.selection_end = None
            self._selecting = False
            self._selection_anchor = None
            if self.selection_rect is not None:
                self.scene.removeItem(self.selection_rect)
                self.selection_rect = None
            if self.on_selection_changed:
                self.on_selection_changed(None)

        def _set_selection(self, start: float, end: float, notify: bool = False) -> None:
            if self.project is None:
                return
            duration = max(self.project.duration, 0.0)
            self.selection_start = max(0.0, min(start, duration))
            self.selection_end = max(0.0, min(end, duration))
            height = self.scene.sceneRect().height()
            if self.selection_rect is not None:
                self.scene.removeItem(self.selection_rect)
            self._draw_selection(height)
            if notify and self.on_selection_changed:
                self.on_selection_changed(self.selection_range())

        def _build_track_geometries(self) -> dict[str, tuple[float, float, int, int]]:
            geometries: dict[str, tuple[float, float, int, int]] = {}
            y = self.chord_height
            for track in self.project.tracks:
                pitch_range = self.pitch_ranges.get(track.name.lower())
                if pitch_range:
                    low_pitch, high_pitch = pitch_range
                    base_height = max(96, (high_pitch - low_pitch + 1) * 8 + 28)
                    height = base_height * self.vertical_zoom
                else:
                    low_pitch = 48
                    high_pitch = 72
                    height = 78 * self.vertical_zoom
                geometries[track.name.lower()] = (y, height, low_pitch, high_pitch)
                y += height
            return geometries

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
                label = self.scene.addText(midi_note_name(pitch))
                label.setDefaultTextColor(QColor("#64748b"))
                label.setPos(84, pitch_y - 5)
                self._make_sticky(label, 84)

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
            if event.button() == Qt.LeftButton and self._start_selection_from_event(event):
                event.accept()
                return
            if event.button() == Qt.LeftButton and self._scrub_from_event(event):
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
            seconds = (point.x() - self.label_width) / self.pixels_per_second
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
                if event.pos().y() <= self.chord_height:
                    self.selected_chord = None
                    if self.on_chord_selected:
                        self.on_chord_selected(None)
                    self.redraw()
                return False
            seconds = self._seconds_from_event(event)
            edge = max(0.04, 8 / self.pixels_per_second)
            if abs(seconds - chord.start) <= edge:
                mode = "resize_start"
            elif abs(seconds - chord.end) <= edge:
                mode = "resize_end"
            else:
                mode = "move"
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

        def _update_chord_edit_from_event(self, event) -> bool:
            if self.project is None or not self._chord_drag:
                return False
            preview = self._dragged_chord_from_event(event)
            self._chord_drag["preview"] = preview
            if self.on_chord_selected:
                self.on_chord_selected(preview)
            return True

        def _finish_chord_edit_from_event(self, event) -> None:
            if not self._chord_drag:
                return
            original = self._chord_drag["chord"]
            edited = self._dragged_chord_from_event(event)
            self._chord_drag = None
            self.unsetCursor()
            self.selected_chord = edited
            if self.on_chord_edited:
                self.on_chord_edited(original, edited)

        def _dragged_chord_from_event(self, event) -> ChordRegion:
            original = self._chord_drag["chord"]
            mode = self._chord_drag["mode"]
            seconds = self._seconds_from_event(event)
            duration = max(0.0, self.project.duration if self.project else original.end)
            minimum = max(0.08, 4 / self.pixels_per_second)
            if mode == "move":
                delta = seconds - self._chord_drag["press_seconds"]
                length = original.duration
                start = max(0.0, min(original.start + delta, max(0.0, duration - length)))
                end = start + length
            elif mode == "resize_start":
                end = original.end
                start = max(0.0, min(seconds, end - minimum))
            else:
                start = original.start
                end = min(duration, max(seconds, start + minimum))
            return ChordRegion(start=start, end=end, label=original.label, confidence=original.confidence)

        def _chord_at_event(self, event) -> ChordRegion | None:
            if self.project is None:
                return None
            point = self.mapToScene(event.pos())
            if point.x() < self.label_width:
                return None
            in_chord_lane = point.y() <= self.chord_height or event.pos().y() <= self.chord_height
            if not in_chord_lane:
                return None
            seconds = self._seconds_from_event(event)
            for chord in reversed(self.project.chords):
                edge_slop = max(0.04, 5 / self.pixels_per_second)
                if chord.start - edge_slop <= seconds <= chord.end + edge_slop:
                    return chord
            return None

        def _seconds_from_event(self, event) -> float:
            point = self.mapToScene(event.pos())
            return max(0.0, (point.x() - self.label_width) / self.pixels_per_second)

        def _start_selection_from_event(self, event) -> bool:
            if self.project is None:
                return False
            point = self.mapToScene(event.pos())
            if point.x() < self.label_width:
                return False
            in_chord_lane = point.y() <= self.chord_height or event.pos().y() <= self.chord_height
            if not in_chord_lane and not (event.modifiers() & Qt.ShiftModifier):
                return False
            seconds = (point.x() - self.label_width) / self.pixels_per_second
            self._selection_anchor = max(0.0, min(seconds, max(self.project.duration, 0.0)))
            self._selecting = True
            self._set_selection(self._selection_anchor, self._selection_anchor)
            return True

        def _update_selection_from_event(self, event, notify: bool = False) -> bool:
            if self.project is None or self._selection_anchor is None:
                return False
            point = self.mapToScene(event.pos())
            seconds = (point.x() - self.label_width) / self.pixels_per_second
            self._set_selection(self._selection_anchor, seconds, notify=notify)
            return True

        def _x(self, seconds: float) -> float:
            return self.label_width + seconds * self.pixels_per_second

        def _view_center_seconds(self) -> float:
            point = self.mapToScene(self.viewport().rect().center())
            return max(0.0, (point.x() - self.label_width) / self.pixels_per_second)

        def _center_on_seconds(self, seconds: float) -> None:
            center = self.mapToScene(self.viewport().rect().center())
            self.centerOn(self._x(seconds), center.y())

    class MainWindow(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("PitchStems")
            self.resize(1220, 780)
            self.choice = model_choice("bs_roformer_sw")
            self.log_path = log_path
            self.logger = logger
            self.messages: queue.Queue[str] = queue.Queue()
            self.worker: threading.Thread | None = None
            self.midi_preview_worker: threading.Thread | None = None
            self.latest_output_dir: Path | None = None
            self.current_result: PipelineResult | None = None
            self.current_stems: list[StemResult] = []
            self.current_input_stem: str | None = None
            self.editor_project: EditorProject | None = None
            self.is_playing = False
            self.track_players: dict[str, QMediaPlayer] = {}
            self.track_audio_outputs: dict[str, QAudioOutput] = {}
            self.midi_players: dict[str, QMediaPlayer] = {}
            self.midi_audio_outputs: dict[str, QAudioOutput] = {}
            self.midi_preview_paths: dict[str, Path] = {}
            self.track_audio_checks: dict[str, QCheckBox] = {}
            self.track_audio_sliders: dict[str, QSlider] = {}
            self.track_midi_checks: dict[str, QCheckBox] = {}
            self.track_midi_sliders: dict[str, QSlider] = {}
            self.activity_depth = 0
            self.manual_chords: list[ChordRegion] = []
            self.removed_chord_ranges: list[tuple[float, float]] = []

            self.drop_zone = DropZone()
            self.drop_zone.on_path_changed = self.reset_stage_state
            self.output_dir = QLineEdit(str(Path.home() / "PitchStems Projects"))
            self.output_dir.setReadOnly(True)
            self.choose_output = QPushButton("Choose Output")
            self.open_project = QPushButton("Open Project")
            self.open_output = QPushButton("Open Output Folder")
            self.open_output.setEnabled(False)

            self.separation_status = QLabel("Not run yet.")
            self.separation_status.setWordWrap(True)
            self.separation_status.setStyleSheet("color: #4b5563;")
            self.midi_status = QLabel("Run the full pipeline first, then MIDI can be rerun without separating again.")
            self.midi_status.setWordWrap(True)
            self.midi_status.setStyleSheet("color: #4b5563;")
            self.workflow_note = QLabel("Use Run separation + MIDI after changing separation/output settings. Use Rerun MIDI only after changing Basic Pitch settings or MIDI stem ticks.")
            self.workflow_note.setWordWrap(True)
            self.workflow_note.setStyleSheet("color: #4b5563;")

            self.model_title = QLabel()
            self.model_title.setStyleSheet("font-size: 18px; font-weight: 700;")
            self.model_summary = QLabel()
            self.model_summary.setWordWrap(True)
            self.model_facts = QLabel()
            self.model_facts.setWordWrap(True)
            self.model_facts.setStyleSheet("color: #374151;")
            self.audio_prep = QLabel(
                "Import prep: FFmpeg converts the dropped file to stereo 44.1 kHz PCM WAV for BS-RoFormer. "
                "Basic Pitch then loads each separated WAV and resamples internally to mono 22.05 kHz."
            )
            self.audio_prep.setWordWrap(True)
            self.audio_prep.setStyleSheet("color: #4b5563;")
            self.model_runtime = QLabel()
            self.model_runtime.setWordWrap(True)
            self.model_backend_detail = QLabel()
            self.model_backend_detail.setWordWrap(True)
            self.model_backend_detail.setStyleSheet("color: #4b5563;")
            self.processing_tabs = QTabWidget()
            self.processing_tabs.setDocumentMode(True)

            self.bs_device = NoWheelComboBox()
            self.bs_device.addItem("Auto: CUDA if available", None)
            self.bs_device.addItem("Force CUDA GPU", "cuda:0")
            self.bs_device.addItem("Force CPU", "cpu")
            self.bs_device_help = QLabel("Official BS-RoFormer device setting. Model quality settings come from the downloaded YAML config.")
            self.bs_device_help.setWordWrap(True)
            self.bs_device_help.setStyleSheet("color: #4b5563;")

            self.stem = NoWheelComboBox()
            self.stem.currentIndexChanged.connect(self.refresh_midi_stem_checks)
            self.generate_midi = QCheckBox("Generate MIDI with Basic Pitch")
            self.generate_midi.setChecked(True)
            self.midi_stem_checks: dict[str, QCheckBox] = {}
            self.midi_stems_layout = QGridLayout()
            self.midi_stems_layout.setHorizontalSpacing(12)
            self.midi_stems_layout.setVerticalSpacing(4)
            self.midi_help = QLabel("Tick the saved stems that Basic Pitch should analyse. Drums are off by default because Basic Pitch is for pitched notes.")
            self.midi_help.setWordWrap(True)
            self.midi_help.setStyleSheet("color: #4b5563;")
            self.onset_threshold = _double_spin(0.0, 1.0, 0.5, 0.05, 2)
            self.onset_threshold.setToolTip("Basic Pitch default: 0.50. Higher means fewer detected note attacks; lower means more sensitive note starts.")
            self.frame_threshold = _double_spin(0.0, 1.0, 0.3, 0.05, 2)
            self.frame_threshold.setToolTip("Basic Pitch default: 0.30. Higher means stricter sustained-note detection; lower keeps more quiet/ambiguous frames.")
            self.minimum_note_length = _double_spin(0.0, 1000.0, 127.7, 10.0, 1)
            self.minimum_note_length.setToolTip("Basic Pitch default: 127.7 ms. Notes shorter than this are filtered out.")
            self.minimum_frequency = _frequency_spin("No lower limit")
            self.minimum_frequency.setToolTip("Basic Pitch default: no lower frequency limit.")
            self.maximum_frequency = _frequency_spin("No upper limit")
            self.maximum_frequency.setToolTip("Basic Pitch default: no upper frequency limit.")
            self.midi_tempo = _double_spin(20.0, 300.0, 120.0, 1.0, 1)
            self.midi_tempo.setToolTip("Basic Pitch default: 120 BPM. This is MIDI metadata, not audio time-stretching.")
            self.melodia_trick = QCheckBox("Melodia post-processing (default on)")
            self.melodia_trick.setChecked(True)
            self.melodia_trick.setToolTip("Basic Pitch default. Helps turn frame/onset predictions into cleaner note events.")
            self.multiple_pitch_bends = QCheckBox("Separate pitch bends for overlapping notes (default off)")
            self.multiple_pitch_bends.setToolTip("Basic Pitch default: off. Useful for expressive material, but can make MIDI more complex.")
            self.save_notes = QCheckBox("Save note-event CSV (default on)")
            self.save_notes.setChecked(True)
            self.save_model_outputs = QCheckBox("Save raw model output NPZ (default off)")
            self.save_model_outputs.setToolTip("Basic Pitch default: off. Technical/debug output: contours, onsets, and note activations.")
            self.sonify_midi = QCheckBox("Render MIDI check audio (default off)")
            self.sonification_samplerate = NoWheelSpinBox()
            self.sonification_samplerate.setRange(8000, 192000)
            self.sonification_samplerate.setSingleStep(1000)
            self.sonification_samplerate.setValue(44100)
            self.sonification_samplerate.setEnabled(False)

            self.create_zip = QCheckBox("Create ZIP export")
            self.create_zip.setChecked(True)
            self.open_when_done = QCheckBox("Open output folder when finished")
            self.open_when_done.setChecked(False)

            self.run_full = QPushButton("Run separation + MIDI")
            self.run_midi = QPushButton("Rerun MIDI only")
            self.run_midi.setEnabled(False)
            self.log = QTextEdit()
            self.log.setReadOnly(True)
            self.editor_summary = QLabel("Run separation + MIDI to build an editor timeline.")
            self.editor_summary.setWordWrap(True)
            self.editor_summary.setStyleSheet("color: #4b5563;")
            self.editor_position = QLabel("00:00.000")
            self.editor_position.setMinimumWidth(86)
            self.current_chord = QLabel("Chord: -")
            self.current_chord.setMinimumWidth(220)
            self.current_chord.setStyleSheet("font-weight: 700; color: #4c1d95;")
            self.chord_context = QLabel("Notes: -")
            self.chord_context.setWordWrap(True)
            self.chord_context.setStyleSheet("color: #475569;")
            self.timeline = TimelineView()
            self.timeline.on_position_changed = self.set_editor_position_seconds
            self.timeline.on_selection_changed = self.set_editor_selection
            self.timeline.on_chord_edited = self.edit_timeline_chord
            self.timeline.on_chord_deleted = self.delete_timeline_chord
            self.timeline.on_chord_selected = self.show_timeline_chord_status
            self.timeline.on_redraw_started = lambda: self.begin_activity("Redrawing timeline...")
            self.timeline.on_redraw_finished = lambda: self.end_activity("Timeline ready")
            self.timeline_slider = QSlider(Qt.Horizontal)
            self.timeline_slider.setRange(0, 0)
            self.timeline_slider.setEnabled(False)
            self.timeline_slider.setVisible(False)
            self.track_list = QListWidget()
            self.track_list.setMaximumWidth(240)
            self.track_list.setAlternatingRowColors(True)
            self.playback_controls = QGridLayout()
            self.playback_controls.setHorizontalSpacing(8)
            self.playback_controls.setVerticalSpacing(4)
            self.track_visibility_checks: dict[str, QCheckBox] = {}
            self.track_note_counts: dict[str, int] = {}
            self.editor_track_visibility: dict[str, bool] = {}
            self.chord_list = QListWidget()
            self.chord_list.setMaximumWidth(240)
            self.chord_list.setAlternatingRowColors(True)
            self.preview_chord_button = QPushButton("Play Chord")
            self.use_chord_button = QPushButton("Use for Selection")
            self.preview_chord_button.setEnabled(False)
            self.use_chord_button.setEnabled(False)
            self.chord_preview_player = QMediaPlayer(self)
            self.chord_preview_output = QAudioOutput(self)
            self.chord_preview_output.setVolume(0.85)
            self.chord_preview_player.setAudioOutput(self.chord_preview_output)
            self.play_button = QPushButton("Play")
            self.stop_button = QPushButton("Stop")
            self.stop_button.setEnabled(False)

            output_row = QHBoxLayout()
            output_row.setSpacing(10)
            output_row.addWidget(QLabel("Output"))
            output_row.addWidget(self.output_dir, 1)

            separation_panel = QVBoxLayout()
            separation_panel.setSpacing(8)
            separation_panel.addWidget(_section_label("Separation stage"))
            intro = QLabel("PitchStems uses one stem model: BS-RoFormer SW six-stem. The checkpoint and YAML config come from the native `bs-roformer-infer` registry.")
            intro.setWordWrap(True)
            intro.setStyleSheet("color: #4b5563;")
            separation_panel.addWidget(intro)
            separation_panel.addWidget(self.workflow_note)
            separation_card = QGroupBox("BS-RoFormer SW six-stem")
            separation_card_layout = QVBoxLayout()
            separation_card_layout.setSpacing(8)
            separation_card_layout.addWidget(self.model_summary)
            separation_card_layout.addWidget(self.model_facts)
            separation_card_layout.addWidget(self.audio_prep)
            separation_card_layout.addWidget(self.separation_status)
            separation_card.setLayout(separation_card_layout)
            separation_panel.addWidget(separation_card)
            midi_stage_card = QGroupBox("MIDI stage")
            midi_stage_layout = QVBoxLayout()
            midi_stage_layout.setSpacing(8)
            midi_stage_layout.addWidget(self.midi_status)
            midi_stage_card.setLayout(midi_stage_layout)
            separation_panel.addWidget(midi_stage_card)
            separation_panel.addStretch(1)

            selected_panel = QVBoxLayout()
            selected_panel.setSpacing(8)
            selected_panel.addWidget(_section_label("Controls"))

            runtime_group = QGroupBox("BS-RoFormer runtime")
            runtime_layout = QVBoxLayout()
            runtime_layout.setSpacing(8)
            runtime_layout.addWidget(self.bs_device)
            runtime_layout.addWidget(self.bs_device_help)
            runtime_group.setLayout(runtime_layout)

            backend_group = QGroupBox("Native backend")
            backend_layout = QVBoxLayout()
            backend_layout.setSpacing(6)
            backend_layout.addWidget(self.model_runtime)
            backend_layout.addWidget(self.model_backend_detail)
            backend_group.setLayout(backend_layout)

            stem_group = QGroupBox("Files to save")
            stem_layout = QVBoxLayout()
            stem_layout.setContentsMargins(10, 8, 10, 8)
            stem_layout.addWidget(self.stem)
            stem_group.setLayout(stem_layout)

            midi_group = QGroupBox("MIDI")
            midi_layout = QVBoxLayout()
            midi_layout.setSpacing(8)
            midi_layout.setContentsMargins(10, 8, 10, 8)
            midi_layout.addWidget(self.generate_midi)
            midi_layout.addLayout(self.midi_stems_layout)
            midi_layout.addWidget(self.midi_help)
            midi_group.setLayout(midi_layout)

            midi_settings_tab = QWidget()
            midi_settings_layout = QVBoxLayout()
            midi_settings_layout.setContentsMargins(8, 8, 8, 8)
            midi_settings_layout.setSpacing(6)
            midi_settings_intro = QLabel("These are Basic Pitch's official `predict_and_save` parameters. Defaults shown here are Basic Pitch defaults.")
            midi_settings_intro.setWordWrap(True)
            midi_settings_intro.setStyleSheet("color: #4b5563;")
            midi_settings_layout.addWidget(midi_settings_intro)
            midi_settings_hint = QLabel("Higher thresholds are stricter and usually create fewer notes. Frequency limits filter the MIDI note range after prediction.")
            midi_settings_hint.setWordWrap(True)
            midi_settings_hint.setStyleSheet("color: #4b5563;")
            midi_settings_layout.addWidget(midi_settings_hint)
            midi_grid = QGridLayout()
            midi_grid.setHorizontalSpacing(10)
            midi_grid.setVerticalSpacing(5)
            _grid_control(midi_grid, 0, 0, "Note starts", "default 0.50", self.onset_threshold)
            _grid_control(midi_grid, 0, 1, "Sustained notes", "default 0.30", self.frame_threshold)
            _grid_control(midi_grid, 1, 0, "Minimum note", "default 127.7 ms", self.minimum_note_length)
            _grid_control(midi_grid, 1, 1, "MIDI tempo", "default 120", self.midi_tempo)
            _grid_control(midi_grid, 2, 0, "Lowest note", "default off", self.minimum_frequency)
            _grid_control(midi_grid, 2, 1, "Highest note", "default off", self.maximum_frequency)
            _grid_control(midi_grid, 3, 0, "Check audio rate", "default 44100", self.sonification_samplerate)
            midi_settings_layout.addLayout(midi_grid)

            midi_checks = QGridLayout()
            midi_checks.setHorizontalSpacing(10)
            midi_checks.setVerticalSpacing(3)
            midi_checks.addWidget(self.melodia_trick, 0, 0)
            midi_checks.addWidget(self.multiple_pitch_bends, 0, 1)
            midi_checks.addWidget(self.save_notes, 1, 0)
            midi_checks.addWidget(self.save_model_outputs, 1, 1)
            midi_checks.addWidget(self.sonify_midi, 2, 0)
            midi_settings_layout.addLayout(midi_checks)
            midi_settings_layout.addStretch(1)
            midi_settings_tab.setLayout(midi_settings_layout)

            export_group = QGroupBox("Export")
            export_layout = QVBoxLayout()
            export_layout.setSpacing(8)
            export_layout.setContentsMargins(10, 8, 10, 8)
            export_layout.addWidget(self.create_zip)
            export_layout.addWidget(self.open_when_done)
            export_group.setLayout(export_layout)

            runtime_tab = QWidget()
            runtime_tab_layout = QVBoxLayout()
            runtime_tab_layout.setContentsMargins(8, 8, 8, 8)
            runtime_tab_layout.setSpacing(8)
            runtime_tab_layout.addWidget(runtime_group)
            runtime_tab_layout.addWidget(backend_group)
            runtime_tab_layout.addWidget(export_group)
            runtime_tab_layout.addStretch(1)
            runtime_tab.setLayout(runtime_tab_layout)

            self.processing_tabs.addTab(midi_settings_tab, "Basic Pitch")
            self.processing_tabs.addTab(runtime_tab, "Runtime")

            selected_panel.addWidget(stem_group)
            selected_panel.addWidget(midi_group)
            selected_panel.addWidget(self.processing_tabs, 1)
            selected_panel.addStretch(1)

            main_row = QHBoxLayout()
            main_row.setSpacing(16)
            main_row.addLayout(separation_panel, 3)
            main_row.addLayout(selected_panel, 2)

            action_row = QHBoxLayout()
            action_row.addStretch(1)
            action_row.addWidget(self.run_midi)
            action_row.addWidget(self.run_full)

            pipeline_layout = QVBoxLayout()
            pipeline_layout.setContentsMargins(12, 12, 12, 12)
            pipeline_layout.setSpacing(10)
            pipeline_layout.addWidget(self.drop_zone)
            pipeline_layout.addLayout(output_row)
            pipeline_layout.addLayout(main_row, 1)
            pipeline_layout.addLayout(action_row)
            pipeline_layout.addWidget(self.log, 1)
            pipeline_page = QWidget()
            pipeline_page.setLayout(pipeline_layout)

            editor_page = QWidget()
            editor_layout = QVBoxLayout()
            editor_layout.setContentsMargins(12, 12, 12, 12)
            editor_layout.setSpacing(10)
            editor_layout.addWidget(self.editor_summary)

            transport_row = QHBoxLayout()
            transport_row.setSpacing(8)
            transport_row.addWidget(self.play_button)
            transport_row.addWidget(self.stop_button)
            transport_row.addWidget(QLabel("Position"))
            transport_row.addWidget(self.editor_position)
            transport_row.addWidget(self.current_chord)
            transport_row.addStretch(1)
            editor_layout.addLayout(transport_row)

            editor_body = QHBoxLayout()
            editor_body.setSpacing(10)
            editor_side = QVBoxLayout()
            editor_side.setSpacing(8)
            editor_side.addWidget(_section_label("Tracks & Mix"))
            editor_side.addLayout(self.playback_controls)
            editor_side.addWidget(_section_label("Chord Inspector"))
            editor_side.addWidget(self.chord_context)
            chord_action_row = QHBoxLayout()
            chord_action_row.setSpacing(6)
            chord_action_row.addWidget(self.preview_chord_button)
            chord_action_row.addWidget(self.use_chord_button)
            editor_side.addLayout(chord_action_row)
            editor_side.addWidget(self.chord_list, 1)
            editor_body.addLayout(editor_side)
            editor_body.addWidget(self.timeline, 1)
            editor_layout.addLayout(editor_body, 1)
            editor_page.setLayout(editor_layout)

            self.main_tabs = QTabWidget()
            self.main_tabs.addTab(pipeline_page, "Pipeline")
            self.main_tabs.addTab(editor_page, "Editor")

            root = QWidget()
            root_layout = QVBoxLayout()
            root_layout.setContentsMargins(0, 0, 0, 0)
            root_layout.addWidget(self.main_tabs)
            root.setLayout(root_layout)
            self.setCentralWidget(root)
            self.create_menus()
            self.activity_label = QLabel("Ready")
            self.activity_label.setMinimumWidth(180)
            self.activity_bar = QProgressBar()
            self.activity_bar.setRange(0, 1)
            self.activity_bar.setValue(1)
            self.activity_bar.setMaximumWidth(150)
            self.activity_bar.setTextVisible(False)
            self.statusBar().addPermanentWidget(self.activity_label)
            self.statusBar().addPermanentWidget(self.activity_bar)
            self.statusBar().showMessage(
                "Timeline: Space plays/pauses; drag chord lane or Shift+drag to select chord-analysis range; Esc clears selection; wheel scrolls, Ctrl+wheel zooms."
            )
            self.space_playback_shortcut = QShortcut(QKeySequence("Space"), self)
            self.space_playback_shortcut.setContext(Qt.ApplicationShortcut)
            self.space_playback_shortcut.activated.connect(self.toggle_playback_from_shortcut)
            self.clear_selection_shortcut = QShortcut(QKeySequence("Esc"), self)
            self.clear_selection_shortcut.setContext(Qt.ApplicationShortcut)
            self.clear_selection_shortcut.activated.connect(self.clear_editor_selection)

            self.run_full.clicked.connect(self.start_full_processing)
            self.run_midi.clicked.connect(self.start_midi_processing)
            self.play_button.clicked.connect(self.toggle_playback)
            self.stop_button.clicked.connect(self.stop_transport)
            self.preview_chord_button.clicked.connect(self.preview_selected_chord)
            self.use_chord_button.clicked.connect(self.assign_selected_chord_to_selection)
            self.chord_list.itemDoubleClicked.connect(self.preview_chord_item)
            self.chord_list.currentItemChanged.connect(lambda *_args: self.refresh_chord_actions())
            self.timeline_slider.valueChanged.connect(self.set_editor_position)
            self.bs_device.currentIndexChanged.connect(self.refresh_model_details)
            self.generate_midi.toggled.connect(self.refresh_midi_stem_checks)
            self.sonify_midi.toggled.connect(self.sonification_samplerate.setEnabled)

            self.refresh_model_details()
            self.drop_zone.setFocus()

            self.timer = QTimer(self)
            self.timer.timeout.connect(self.flush_messages)
            self.timer.start(100)

            self.transport_timer = QTimer(self)
            self.transport_timer.timeout.connect(self.update_transport_position)

        def begin_activity(self, message: str, busy: bool = True) -> None:
            self.activity_depth += 1
            self.activity_label.setText(message)
            self.statusBar().showMessage(message)
            if busy:
                self.activity_bar.setRange(0, 0)
            else:
                self.activity_bar.setRange(0, 1)
                self.activity_bar.setValue(0)
            QApplication.processEvents()

        def end_activity(self, message: str = "Ready") -> None:
            self.activity_depth = max(0, self.activity_depth - 1)
            if self.activity_depth:
                return
            self.activity_label.setText(message)
            self.activity_bar.setRange(0, 1)
            self.activity_bar.setValue(1)
            self.statusBar().showMessage(message, 4000)
            QApplication.processEvents()

        def set_activity_message(self, message: str) -> None:
            self.activity_label.setText(message)
            self.statusBar().showMessage(message)
            QApplication.processEvents()

        def create_menus(self) -> None:
            file_menu = self.menuBar().addMenu("&File")
            self._add_action(file_menu, "&Open Audio...", "Ctrl+O", self.pick_audio)
            self._add_action(file_menu, "Open &Project...", "Ctrl+Shift+O", self.pick_project)
            file_menu.addSeparator()
            self._add_action(file_menu, "&Save Project", "Ctrl+S", self.save_project_now)
            self._add_action(file_menu, "Choose Output &Folder...", None, self.pick_output_dir)
            self._add_action(file_menu, "Open Output Folder", "Ctrl+E", self.open_latest_output)
            self._add_action(file_menu, "Open Logs Folder", None, self.open_logs_folder)
            file_menu.addSeparator()
            self._add_action(file_menu, "E&xit", "Alt+F4", self.close)

            run_menu = self.menuBar().addMenu("&Run")
            self._add_action(run_menu, "Run Separation + MIDI", "F5", self.start_full_processing)
            self._add_action(run_menu, "Rerun MIDI Only", "Shift+F5", self.start_midi_processing)

            view_menu = self.menuBar().addMenu("&View")
            self._add_action(view_menu, "Pipeline", "Ctrl+1", lambda: self.main_tabs.setCurrentIndex(0))
            self._add_action(view_menu, "Editor", "Ctrl+2", lambda: self.main_tabs.setCurrentIndex(1))
            view_menu.addSeparator()
            zoom_time_in = self._add_action(
                view_menu,
                "Zoom Time In",
                None,
                lambda: self.timeline.zoom_horizontal(1.18),
            )
            zoom_time_in.setShortcuts([QKeySequence("Ctrl++"), QKeySequence("Ctrl+=")])
            self._add_action(view_menu, "Zoom Time Out", "Ctrl+-", lambda: self.timeline.zoom_horizontal(1 / 1.18))
            self._add_action(
                view_menu,
                "Zoom Pitch In",
                "Ctrl+Shift++",
                lambda: self.timeline.zoom_vertical(1.18),
            )
            self._add_action(
                view_menu,
                "Zoom Pitch Out",
                "Ctrl+Shift+-",
                lambda: self.timeline.zoom_vertical(1 / 1.18),
            )
            self._add_action(view_menu, "Reset Timeline Zoom", "Ctrl+0", self.timeline.reset_zoom)

            help_menu = self.menuBar().addMenu("&Help")
            self._add_action(help_menu, "Show Timeline Controls", None, self.show_timeline_controls)

        def _add_action(self, menu, text: str, shortcut: str | None, callback) -> QAction:
            action = QAction(text, self)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(callback)
            menu.addAction(action)
            return action

        def show_timeline_controls(self) -> None:
            self.statusBar().showMessage(
                "Timeline controls: Space plays/pauses; drag the chord lane or Shift+drag the timeline to select a chord-analysis range; Esc clears selection; click/drag sets playhead; wheel scrolls vertically; Shift+wheel scrolls horizontally; Ctrl+wheel zooms time; Ctrl+Shift+wheel zooms pitch; middle/right drag pans.",
                12000,
            )

        def toggle_playback_from_shortcut(self) -> None:
            focused = QApplication.focusWidget()
            interactive_widgets = (
                QCheckBox,
                QComboBox,
                QDoubleSpinBox,
                QLineEdit,
                QListWidget,
                QPushButton,
                QSlider,
                QSpinBox,
                QTextEdit,
            )
            if isinstance(focused, interactive_widgets):
                return
            self.toggle_playback()

        def pick_audio(self) -> None:
            filename, _selected_filter = QFileDialog.getOpenFileName(
                self,
                "Open audio",
                str(Path.home()),
                "Audio files (*.wav *.mp3 *.flac *.m4a *.aac *.ogg);;All files (*.*)",
            )
            if filename:
                self.set_audio_path(Path(filename))

        def set_audio_path(self, path: Path) -> None:
            self.drop_zone.set_audio_file(path)
            self.reset_stage_state(path)

        def save_project_now(self) -> None:
            if self.current_result is None:
                self.append_log("No project is open yet.")
                return
            self.save_editor_state()
            self.append_log(f"Saved project: {self.current_result.project_dir / PROJECT_FILENAME}")

        def pick_output_dir(self) -> None:
            directory = QFileDialog.getExistingDirectory(self, "Choose output directory")
            if directory:
                self.output_dir.setText(directory)

        def pick_project(self) -> None:
            filename, _selected_filter = QFileDialog.getOpenFileName(
                self,
                "Open PitchStems project",
                str(Path(self.output_dir.text())),
                f"PitchStems Project ({PROJECT_FILENAME});;JSON files (*.json)",
            )
            if not filename:
                return
            self.begin_activity("Opening project...")
            try:
                self.logger.info("Opening project manifest: %s", filename)
                result = load_pipeline_result(Path(filename))
            except Exception as exc:
                self.logger.exception("Could not open project manifest")
                self.append_log(f"Could not open project: {exc}")
                self.end_activity("Could not open project")
                return
            self.output_dir.setText(str(result.project_dir.parent))
            self.drop_zone.set_project_file(result.project_dir, result.source_audio)
            try:
                self.logger.info("Building editor for project: %s", result.project_dir)
                self.set_current_result(result, open_output=False)
            except Exception as exc:
                self.logger.exception("Could not open project editor")
                self.append_log(f"Could not open project editor: {exc}")
                self.append_log(f"Log file: {self.log_path}")
                self.reset_stage_state()
                self.end_activity("Could not open project editor")
                return
            self.append_log(f"Opened project: {result.project_dir}")
            self.end_activity("Project loaded")

        def start_full_processing(self) -> None:
            if self.worker and self.worker.is_alive():
                return
            if not self.drop_zone.path:
                self.append_log("Drop an audio file first.")
                return

            self.set_processing_state(True)
            self.begin_activity("Running separation + MIDI...")
            self.open_output.setEnabled(False)
            self.append_log("Starting separation + MIDI pipeline...")
            self.worker = threading.Thread(target=self.run_full_pipeline, daemon=True)
            self.worker.start()

        def start_midi_processing(self) -> None:
            if self.worker and self.worker.is_alive():
                return
            if not self.current_result or not self.current_stems or not self.current_input_stem:
                self.append_log("Run separation first. Then MIDI can be rerun from those stems.")
                return

            self.set_processing_state(True)
            self.begin_activity("Rerunning MIDI...")
            self.append_log("Rerunning MIDI from existing stems...")
            self.worker = threading.Thread(target=self.run_midi_stage, daemon=True)
            self.worker.start()

        def run_full_pipeline(self) -> None:
            try:
                midi_stems = self.selected_midi_stems()
                self.logger.info("Starting full pipeline for %s", self.drop_zone.path)
                result = process_audio_file(
                    self.drop_zone.path,
                    Path(self.output_dir.text()),
                    separation_options=self.selected_separation_options(),
                    generate_midi=self.generate_midi.isChecked() and bool(midi_stems),
                    midi_policy="all",
                    midi_options=self.selected_midi_options(),
                    midi_stems=midi_stems,
                    create_zip=self.create_zip.isChecked(),
                    log=self.messages.put,
                )
                self.messages.put(("RESULT", result))
                self.messages.put(f"Export ready: {result.zip_path or result.project_dir / 'export'}")
            except Exception as exc:
                self.logger.exception("Full pipeline failed")
                self.messages.put(f"Error: {exc}")
            finally:
                self.messages.put("__ENABLE_PROCESS__")

        def run_midi_stage(self) -> None:
            try:
                midi_stems = self.selected_midi_stems()
                self.logger.info("Starting MIDI rerun for %s", self.current_result.project_dir)
                result = process_midi_from_stems(
                    project_dir=self.current_result.project_dir,
                    input_stem=self.current_input_stem,
                    normalized_audio=self.current_result.normalized_audio,
                    stems=self.current_stems,
                    midi_policy="all",
                    midi_options=self.selected_midi_options(),
                    midi_stems=midi_stems,
                    create_zip=self.create_zip.isChecked(),
                    log=self.messages.put,
                )
                self.messages.put(("RESULT", result))
                self.messages.put(f"Updated MIDI export: {result.zip_path or result.project_dir / 'export'}")
            except Exception as exc:
                self.logger.exception("MIDI rerun failed")
                self.messages.put(f"Error: {exc}")
            finally:
                self.messages.put("__ENABLE_PROCESS__")

        def flush_messages(self) -> None:
            while True:
                try:
                    message = self.messages.get_nowait()
                except queue.Empty:
                    return
                if isinstance(message, tuple) and message[0] == "RESULT":
                    self.set_current_result(message[1])
                elif isinstance(message, tuple) and message[0] == "MIDI_PREVIEWS":
                    self.attach_midi_preview_players(message[1])
                elif isinstance(message, tuple) and message[0] == "MIDI_PREVIEW_FAILED":
                    self.append_log(message[1])
                    self.end_activity("MIDI preview audio failed")
                elif message == "__ENABLE_PROCESS__":
                    self.set_processing_state(False)
                    self.end_activity("Processing complete")
                elif message.startswith("__OUTPUT_DIR__"):
                    self.latest_output_dir = Path(message.removeprefix("__OUTPUT_DIR__"))
                    self.open_output.setEnabled(True)
                    if self.open_when_done.isChecked():
                        self.open_latest_output()
                else:
                    self.append_log(message)
                    if message and not message.startswith("Tracks:"):
                        self.set_activity_message(message[:120])

        def append_log(self, message: str) -> None:
            self.logger.info(message)
            self.log.append(message)

        def set_current_result(self, result: PipelineResult, open_output: bool = True) -> None:
            self.logger.info("Setting current result: %s", result.project_dir)
            self.set_activity_message("Loading result...")
            self.current_result = result
            self.current_stems = result.stems
            self.current_input_stem = (result.source_audio or result.normalized_audio).stem
            self.latest_output_dir = result.project_dir / "export"
            self.open_output.setEnabled(True)
            self.run_midi.setEnabled(True)
            self.separation_status.setText(f"Ready: {len(result.stems)} stems saved in {result.project_dir / 'stems'}")
            self.midi_status.setText(
                f"Ready: {len(result.midi_files)} MIDI files. Change Basic Pitch settings or MIDI stem ticks, then use Rerun MIDI only."
            )
            self.load_editor_project(result)
            if open_output and self.open_when_done.isChecked():
                self.open_latest_output()

        def load_editor_project(self, result: PipelineResult) -> None:
            self.logger.info("Building editor project model")
            self.set_activity_message("Building editor project...")
            self.editor_project = build_editor_project(result)
            editor_state = self.load_editor_state(result)
            self.manual_chords = self.chord_overrides_from_editor_state(editor_state)
            self.removed_chord_ranges = self.chord_removals_from_editor_state(editor_state)
            self.apply_manual_chords()
            self.logger.info(
                "Editor model built: tracks=%d notes=%d chords=%d",
                len(self.editor_project.tracks),
                len(self.editor_project.notes),
                len(self.editor_project.chords),
            )
            project = self.editor_project
            track_visibility = editor_state.get("track_visibility", {})
            playhead_seconds = float(editor_state.get("playhead_seconds", 0.0) or 0.0)
            self.editor_summary.setText(
                f"Editor project: {len(project.tracks)} tracks, {len(project.notes)} notes, "
                f"{len(project.chords)} chord regions."
            )
            maximum = max(0, int(project.duration * 1000))
            self.timeline_slider.blockSignals(True)
            self.timeline_slider.setRange(0, maximum)
            self.timeline_slider.setValue(0)
            self.timeline_slider.setEnabled(maximum > 0)
            self.timeline_slider.blockSignals(False)
            self.editor_position.setText(_format_time(playhead_seconds))
            self.refresh_editor_lists(track_visibility)
            self.refresh_playback_controls(editor_state)
            self.clear_transport_players()
            self.logger.info("Drawing editor timeline")
            self.set_activity_message("Drawing editor timeline...")
            self.timeline.set_project(project)
            self.timeline.set_visible_tracks(
                {track.name for track in project.tracks if track_visibility.get(track.name, True)}
            )
            self.set_editor_position_seconds(playhead_seconds)
            self.main_tabs.setCurrentIndex(1)
            self.logger.info("Editor project loaded")

        def chord_overrides_from_editor_state(self, editor_state: dict) -> list[ChordRegion]:
            chords: list[ChordRegion] = []
            for item in editor_state.get("chord_overrides", []):
                try:
                    start = float(item.get("start", 0.0))
                    end = float(item.get("end", 0.0))
                    label = str(item.get("label", "")).strip()
                    confidence = float(item.get("confidence", 1.0))
                except (TypeError, ValueError):
                    continue
                if label and end > start:
                    chords.append(ChordRegion(start=start, end=end, label=label, confidence=confidence))
            return sorted(chords, key=lambda chord: (chord.start, chord.end, chord.label))

        def chord_removals_from_editor_state(self, editor_state: dict) -> list[tuple[float, float]]:
            ranges: list[tuple[float, float]] = []
            for item in editor_state.get("chord_removals", []):
                try:
                    start = float(item.get("start", 0.0))
                    end = float(item.get("end", 0.0))
                except (TypeError, ValueError):
                    continue
                if end > start:
                    ranges.append((start, end))
            return sorted(ranges)

        def apply_manual_chords(self) -> None:
            if self.editor_project is None or (not self.manual_chords and not self.removed_chord_ranges):
                return
            chords = list(self.editor_project.chords)
            for start, end in self.removed_chord_ranges:
                chords = [chord for chord in chords if chord.end <= start or chord.start >= end]
            for manual in self.manual_chords:
                chords = [chord for chord in chords if chord.end <= manual.start or chord.start >= manual.end]
                chords.append(manual)
            self.editor_project = replace(
                self.editor_project,
                chords=sorted(chords, key=lambda chord: (chord.start, chord.end, chord.label)),
            )

        def refresh_editor_project_from_chord_edits(self, selected_chord: ChordRegion | None = None) -> None:
            if self.current_result is None:
                return
            self.editor_project = build_editor_project(self.current_result)
            self.apply_manual_chords()
            self.timeline.set_project(self.editor_project)
            self.timeline.set_visible_tracks(
                {
                    stem_name
                    for stem_name, checkbox in self.track_visibility_checks.items()
                    if checkbox.isChecked()
                }
            )
            self.timeline.selected_chord = selected_chord
            self.timeline.redraw()
            self.refresh_detected_chord_list()
            self.save_editor_state()

        def load_editor_state(self, result: PipelineResult) -> dict:
            try:
                manifest = load_project_manifest(result.project_dir / PROJECT_FILENAME)
            except Exception:
                return {}
            return manifest.get("editor", {})

        def refresh_editor_lists(self, track_visibility: dict[str, bool] | None = None) -> None:
            track_visibility = track_visibility or {}
            self.editor_track_visibility = track_visibility
            self.track_note_counts = {}
            self.chord_list.clear()
            if self.editor_project is None:
                return
            for note in self.editor_project.notes:
                self.track_note_counts[note.stem] = self.track_note_counts.get(note.stem, 0) + 1
            self.refresh_detected_chord_list()

        def refresh_detected_chord_list(self) -> None:
            self.chord_list.clear()
            if self.editor_project is None:
                return
            for chord in self.editor_project.chords[:200]:
                self.chord_list.addItem(
                    f"{_format_time(chord.start)}  {chord.label}  ({chord.confidence:.0%})"
                )
            if len(self.editor_project.chords) > 200:
                self.chord_list.addItem(f"... {len(self.editor_project.chords) - 200} more")
            self.refresh_chord_actions()

        def set_editor_position(self, value: int) -> None:
            self.set_editor_position_seconds(value / 1000)

        def refresh_playback_controls(self, editor_state: dict) -> None:
            _clear_layout(self.playback_controls)
            self.track_audio_checks.clear()
            self.track_audio_sliders.clear()
            self.track_midi_checks.clear()
            self.track_midi_sliders.clear()
            self.track_visibility_checks.clear()
            if self.editor_project is None:
                return

            track_visibility = self.editor_track_visibility
            audio_enabled = editor_state.get("track_audio_enabled", {})
            audio_volume = editor_state.get("track_audio_volume", {})
            midi_enabled = editor_state.get("track_midi_enabled", {})
            midi_volume = editor_state.get("track_midi_volume", {})

            for column, text in enumerate(["Show", "Stem", "Audio", "Vol", "MIDI", "Vol", "Notes"]):
                label = QLabel(text)
                label.setStyleSheet("font-weight: 600; color: #334155;")
                self.playback_controls.addWidget(label, 0, column)

            for row, track in enumerate(self.editor_project.tracks, 1):
                show_check = QCheckBox()
                show_check.setChecked(track_visibility.get(track.name, True))
                show_check.setToolTip("Show this track's MIDI notes in the timeline.")
                show_check.toggled.connect(lambda *_args: self.refresh_visible_tracks())
                show_check.toggled.connect(lambda *_args: self.save_editor_state())
                self.track_visibility_checks[track.name] = show_check
                self.playback_controls.addWidget(show_check, row, 0)

                name = QLabel(track.name)
                name.setMinimumWidth(58)
                self.playback_controls.addWidget(name, row, 1)

                audio_check = QCheckBox()
                audio_check.setChecked(audio_enabled.get(track.name, True))
                audio_check.setToolTip("Play this separated stem audio in the editor transport.")
                audio_slider = QSlider(Qt.Horizontal)
                audio_slider.setRange(0, 100)
                audio_slider.setValue(int(audio_volume.get(track.name, 80)))
                audio_slider.setFixedWidth(82)
                audio_slider.setToolTip("Separated stem audio volume.")
                audio_check.toggled.connect(lambda *_args: self.refresh_playback_mix())
                audio_check.toggled.connect(lambda *_args: self.save_editor_state())
                audio_slider.valueChanged.connect(lambda *_args: self.refresh_playback_mix())
                audio_slider.valueChanged.connect(lambda *_args: self.save_editor_state())
                self.track_audio_checks[track.name] = audio_check
                self.track_audio_sliders[track.name] = audio_slider
                self.playback_controls.addWidget(audio_check, row, 2)
                self.playback_controls.addWidget(audio_slider, row, 3)

                midi_check = QCheckBox()
                midi_check.setChecked(midi_enabled.get(track.name, False))
                midi_check.setEnabled(False)
                midi_check.setToolTip("MIDI synth playback will be added in the next playback pass.")
                midi_slider = QSlider(Qt.Horizontal)
                midi_slider.setRange(0, 100)
                midi_slider.setValue(int(midi_volume.get(track.name, 70)))
                midi_slider.setFixedWidth(82)
                midi_slider.setEnabled(False)
                midi_slider.setToolTip("Reserved for MIDI synth playback volume.")
                midi_check.toggled.connect(lambda *_args: self.refresh_playback_mix())
                midi_check.toggled.connect(lambda *_args: self.save_editor_state())
                midi_slider.valueChanged.connect(lambda *_args: self.refresh_playback_mix())
                midi_slider.valueChanged.connect(lambda *_args: self.save_editor_state())
                self.track_midi_checks[track.name] = midi_check
                self.track_midi_sliders[track.name] = midi_slider
                self.playback_controls.addWidget(midi_check, row, 4)
                self.playback_controls.addWidget(midi_slider, row, 5)

                notes = QLabel(str(self.track_note_counts.get(track.name, 0)))
                notes.setStyleSheet("color: #64748b;")
                self.playback_controls.addWidget(notes, row, 6)

        def prepare_transport_players(self, result: PipelineResult) -> None:
            self.set_activity_message("Preparing audio players...")
            self.pause_transport()
            self.clear_transport_players()
            self.midi_preview_paths = self.find_existing_midi_previews(result)
            for stem in result.stems:
                player = QMediaPlayer(self)
                output = QAudioOutput(self)
                player.setAudioOutput(output)
                player.setSource(QUrl.fromLocalFile(str(stem.path)))
                self.track_players[stem.name] = player
                self.track_audio_outputs[stem.name] = output
            self.attach_midi_preview_players(self.midi_preview_paths)
            self.start_midi_preview_render(result)
            self.refresh_playback_mix()

        def clear_transport_players(self) -> None:
            for player in self.transport_players():
                try:
                    player.pause()
                    player.setSource(QUrl())
                except RuntimeError:
                    self.logger.exception("Transport player cleanup failed")
            self.track_players.clear()
            self.track_audio_outputs.clear()
            self.midi_players.clear()
            self.midi_audio_outputs.clear()
            self.midi_preview_paths.clear()

        def transport_players(self) -> list[QMediaPlayer]:
            return list(self.track_players.values()) + list(self.midi_players.values())

        def find_existing_midi_previews(self, result: PipelineResult) -> dict[str, Path]:
            preview_dir = result.project_dir / "editor" / "midi-preview"
            previews = {}
            for stem in result.stems:
                preview = preview_dir / f"{stem.name}_midi_preview.wav"
                if preview.exists():
                    previews[stem.name] = preview
            return previews

        def start_midi_preview_render(self, result: PipelineResult) -> None:
            if self.editor_project is None or not self.editor_project.notes:
                return
            if self.midi_preview_worker and self.midi_preview_worker.is_alive():
                return
            missing = [
                track.name
                for track in self.editor_project.tracks
                if track.name not in self.midi_preview_paths
                and any(note.stem.lower() == track.name.lower() for note in self.editor_project.notes)
            ]
            if not missing:
                return
            project = self.editor_project
            preview_dir = result.project_dir / "editor" / "midi-preview"
            self.append_log(f"Rendering MIDI preview audio for {len(missing)} tracks in the background...")
            self.begin_activity("Rendering MIDI preview audio...")

            def worker() -> None:
                previews: dict[str, Path] = {}
                try:
                    for stem_name in missing:
                        preview = render_midi_preview(
                            stem_name,
                            project.notes,
                            preview_dir,
                            project.duration,
                        )
                        if preview:
                            previews[stem_name] = preview
                    self.messages.put(("MIDI_PREVIEWS", previews))
                except Exception as exc:
                    self.logger.exception("MIDI preview render failed")
                    self.messages.put(("MIDI_PREVIEW_FAILED", f"Could not render MIDI previews: {exc}"))

            self.midi_preview_worker = threading.Thread(target=worker, daemon=True)
            self.midi_preview_worker.start()

        def attach_midi_preview_players(self, previews: dict[str, Path]) -> None:
            if not previews:
                self.end_activity("No MIDI preview audio rendered")
                return
            self.midi_preview_paths.update(previews)
            for stem_name, midi_preview in previews.items():
                if stem_name in self.midi_players:
                    continue
                midi_player = QMediaPlayer(self)
                midi_output = QAudioOutput(self)
                midi_player.setAudioOutput(midi_output)
                midi_player.setSource(QUrl.fromLocalFile(str(midi_preview)))
                self.midi_players[stem_name] = midi_player
                self.midi_audio_outputs[stem_name] = midi_output
                midi_check = self.track_midi_checks.get(stem_name)
                midi_slider = self.track_midi_sliders.get(stem_name)
                if midi_check:
                    midi_check.setEnabled(True)
                    midi_check.setToolTip("Play the generated MIDI preview audio for this stem.")
                if midi_slider:
                    midi_slider.setEnabled(True)
                    midi_slider.setToolTip("MIDI preview audio volume.")
            self.refresh_playback_mix()
            self.append_log(f"MIDI preview audio ready: {len(previews)} tracks.")
            self.end_activity("MIDI preview audio ready")

        def refresh_playback_mix(self) -> None:
            for stem_name, output in self.track_audio_outputs.items():
                enabled = self.track_audio_checks.get(stem_name)
                slider = self.track_audio_sliders.get(stem_name)
                is_enabled = enabled.isChecked() if enabled else True
                volume = slider.value() / 100 if slider else 0.8
                output.setVolume(volume if is_enabled else 0.0)
            for stem_name, output in self.midi_audio_outputs.items():
                enabled = self.track_midi_checks.get(stem_name)
                slider = self.track_midi_sliders.get(stem_name)
                is_enabled = enabled.isChecked() if enabled else False
                volume = slider.value() / 100 if slider else 0.7
                output.setVolume(volume if is_enabled else 0.0)

        def toggle_playback(self) -> None:
            if self.is_playing:
                self.pause_transport()
            else:
                self.play_transport()

        def play_transport(self) -> None:
            if self.editor_project is None or self.current_result is None:
                self.append_log("Open or run a project before playback.")
                return
            if not self.track_players:
                self.append_log("Preparing playback...")
                self.begin_activity("Preparing playback...")
                self.prepare_transport_players(self.current_result)
                self.end_activity("Playback ready")
            self.refresh_playback_mix()
            start_position = self.loop_playback_start_seconds()
            if start_position != self.timeline.position:
                self.set_editor_position_seconds(start_position, save=False, seek_players=False)
            position_ms = int(start_position * 1000)
            for player in self.transport_players():
                player.setPosition(position_ms)
                player.play()
            self.is_playing = True
            self.play_button.setText("Pause")
            self.stop_button.setEnabled(True)
            self.transport_timer.start(80)

        def pause_transport(self) -> None:
            if not self.is_playing:
                return
            for player in self.transport_players():
                player.pause()
            self.is_playing = False
            self.play_button.setText("Play")
            self.transport_timer.stop()
            self.save_editor_state()

        def stop_transport(self) -> None:
            self.is_playing = False
            self.play_button.setText("Play")
            self.stop_button.setEnabled(False)
            self.transport_timer.stop()
            for player in self.transport_players():
                try:
                    player.pause()
                    player.setPosition(0)
                except RuntimeError:
                    self.logger.exception("Transport stop failed")
            if self.editor_project is not None:
                self.set_editor_position_seconds(0.0, seek_players=False)

        def seek_audio_players(self, seconds: float) -> None:
            if not self.track_players:
                return
            position_ms = int(seconds * 1000)
            for player in self.transport_players():
                player.setPosition(position_ms)

        def update_transport_position(self) -> None:
            master = next(iter(self.track_players.values()), None)
            if master is None:
                return
            seconds = master.position() / 1000
            selection = self.timeline.selection_range()
            if selection is not None:
                start, end = selection
                if seconds >= end:
                    self.seek_audio_players(start)
                    self.set_editor_position_seconds(start, save=False, seek_players=False)
                    return
            self.set_editor_position_seconds(seconds, save=False, seek_players=False)

        def loop_playback_start_seconds(self) -> float:
            selection = self.timeline.selection_range()
            if selection is None:
                return self.timeline.position
            start, end = selection
            if start <= self.timeline.position < end:
                return self.timeline.position
            return start

        def set_editor_position_seconds(
            self,
            seconds: float,
            save: bool = True,
            seek_players: bool = True,
        ) -> None:
            if self.editor_project is not None:
                seconds = max(0.0, min(seconds, max(self.editor_project.duration, 0.0)))
            value = int(seconds * 1000)
            self.timeline_slider.blockSignals(True)
            self.timeline_slider.setValue(value)
            self.timeline_slider.blockSignals(False)
            self.editor_position.setText(_format_time(seconds))
            self.timeline.set_position(seconds)
            self.refresh_current_harmony(seconds)
            if seek_players:
                self.seek_audio_players(seconds)
            if save:
                self.save_editor_state()

        def set_editor_selection(self, selection: tuple[float, float] | None) -> None:
            self.refresh_current_harmony(self.timeline.position)
            self.refresh_chord_actions()
            if selection is None:
                self.statusBar().showMessage("Timeline selection cleared.", 3000)
                return
            start, end = selection
            self.statusBar().showMessage(
                f"Loop selection active: {_format_time(start)} - {_format_time(end)}. Press Play to loop this range.",
                5000,
            )

        def clear_editor_selection(self) -> None:
            self.timeline.clear_selection()
            self.refresh_current_harmony(self.timeline.position)

        def refresh_current_harmony(self, seconds: float) -> None:
            if self.editor_project is None:
                self.current_chord.setText("Chord: -")
                self.chord_context.setText("Notes: -")
                self.chord_list.clear()
                return
            selection = self.timeline.selection_range()
            if selection is not None:
                start, end = selection
                analysis = analyze_chord_region(self.editor_project.notes, start, end)
                chord = analysis.label or "No clear chord"
                self.current_chord.setText(
                    f"Selection: {chord}  ({analysis.confidence:.0%})  "
                    f"{_format_time(start)} - {_format_time(end)}"
                )
                self._set_chord_candidates(analysis)
                if analysis.note_weights:
                    note_text = ", ".join(
                        f"{name} ({weight:.0%})"
                        for name, weight in analysis.note_weights[:12]
                    )
                    self.chord_context.setText(f"Weighted notes: {note_text}")
                elif analysis.active_note_names:
                    note_text = ", ".join(analysis.active_note_names[:32])
                    if len(analysis.active_note_names) > 32:
                        note_text += f", +{len(analysis.active_note_names) - 32} more"
                    self.chord_context.setText(f"Notes in selection: {note_text}")
                else:
                    self.chord_context.setText("Notes in selection: -")
                return

            analysis = analyze_chord_at(self.editor_project.notes, seconds)
            active_notes = active_notes_at(self.editor_project.notes, seconds)
            chord = analysis.label or "No clear chord"
            self.current_chord.setText(f"Chord: {chord}  ({analysis.confidence:.0%})")
            self._set_chord_candidates(analysis)
            if active_notes:
                unique_pitches = sorted({note.pitch for note in active_notes})
                shown_pitches = unique_pitches[:32]
                note_text = ", ".join(midi_note_name(pitch) for pitch in shown_pitches)
                if len(unique_pitches) > len(shown_pitches):
                    note_text += f", +{len(unique_pitches) - len(shown_pitches)} more"
                self.chord_context.setText(f"Notes: {note_text}")
            else:
                self.chord_context.setText("Notes: -")

        def _set_chord_candidates(self, analysis) -> None:
            if analysis.candidates:
                self.chord_list.clear()
                for label, confidence in analysis.candidates:
                    note_names = analysis.candidate_notes.get(label, [])
                    notes = self._candidate_notes_text(analysis, label)
                    item = QListWidgetItem(f"{label}  {confidence:.0%}\n{notes}")
                    item.setData(Qt.UserRole, label)
                    item.setData(Qt.UserRole + 1, confidence)
                    item.setData(Qt.UserRole + 2, note_names)
                    item.setToolTip(
                        f"{label}\n"
                        f"Official chord tones: {notes}\n"
                        f"Detector confidence: {confidence:.0%}\n\n"
                        + "\n".join(analysis.candidate_explanations.get(label, []))
                    )
                    self.chord_list.addItem(item)
            else:
                self.chord_list.clear()
                self.chord_list.addItem("No chord candidates here.")
            self.refresh_chord_actions()

        def _candidate_notes_text(self, analysis, label: str) -> str:
            notes = analysis.candidate_notes.get(label, [])
            if not notes:
                return "-"
            text = " - ".join(notes)
            if "/" in label:
                text += f"  bass {label.split('/', 1)[1]}"
            return text

        def refresh_chord_actions(self) -> None:
            item = self.chord_list.currentItem()
            has_candidate = bool(item and item.data(Qt.UserRole))
            self.preview_chord_button.setEnabled(has_candidate)
            self.use_chord_button.setEnabled(has_candidate and self.timeline.selection_range() is not None)

        def preview_selected_chord(self) -> None:
            self.preview_chord_item(self.chord_list.currentItem())

        def preview_chord_item(self, item) -> None:
            if item is None or self.current_result is None:
                return
            label = item.data(Qt.UserRole)
            note_names = item.data(Qt.UserRole + 2) or []
            if not label or not note_names:
                return
            notes = self.preview_notes_for_chord(label, note_names)
            preview_dir = self.current_result.project_dir / "editor" / "chord-preview"
            preview = render_note_preview("official-chord", notes, preview_dir)
            if not preview:
                return
            self.chord_preview_player.pause()
            self.chord_preview_player.setSource(QUrl.fromLocalFile(str(preview)))
            self.chord_preview_player.play()
            self.statusBar().showMessage(f"Playing official {label} chord.", 3000)

        def preview_notes_for_chord(self, label: str, note_names: list[str]) -> list[NoteEvent]:
            pitches = _chord_preview_pitches(label, note_names)
            return [
                NoteEvent(
                    stem="official-chord",
                    start=0.0,
                    end=1.45,
                    pitch=pitch,
                    velocity=92,
                )
                for pitch in pitches
            ]

        def assign_selected_chord_to_selection(self) -> None:
            if self.editor_project is None or self.current_result is None:
                return
            selection = self.timeline.selection_range()
            item = self.chord_list.currentItem()
            if selection is None or item is None:
                return
            label = item.data(Qt.UserRole)
            confidence = float(item.data(Qt.UserRole + 1) or 1.0)
            if not label:
                return
            start, end = selection
            manual = ChordRegion(start=start, end=end, label=label, confidence=confidence)
            self.insert_manual_chord(manual)
            self.refresh_editor_project_from_chord_edits(manual)
            self.statusBar().showMessage(
                f"Assigned {label} to {_format_time(start)} - {_format_time(end)}.",
                5000,
            )

        def insert_manual_chord(self, chord: ChordRegion) -> None:
            self.manual_chords = [
                existing
                for existing in self.manual_chords
                if existing.end <= chord.start or existing.start >= chord.end
            ]
            self.removed_chord_ranges = self._merge_chord_ranges(
                [*self.removed_chord_ranges, (chord.start, chord.end)]
            )
            self.manual_chords.append(chord)
            self.manual_chords.sort(key=lambda item: (item.start, item.end, item.label))

        def edit_timeline_chord(self, original: ChordRegion, edited: ChordRegion) -> None:
            self.removed_chord_ranges = self._merge_chord_ranges(
                [*self.removed_chord_ranges, (original.start, original.end), (edited.start, edited.end)]
            )
            self.manual_chords = [chord for chord in self.manual_chords if chord != original]
            self.insert_manual_chord(edited)
            self.refresh_editor_project_from_chord_edits(edited)
            self.statusBar().showMessage(
                f"Moved {edited.label} to {_format_time(edited.start)} - {_format_time(edited.end)}.",
                5000,
            )

        def delete_timeline_chord(self, chord: ChordRegion) -> None:
            self.removed_chord_ranges = self._merge_chord_ranges(
                [*self.removed_chord_ranges, (chord.start, chord.end)]
            )
            self.manual_chords = [manual for manual in self.manual_chords if manual != chord]
            self.refresh_editor_project_from_chord_edits(None)
            self.statusBar().showMessage(f"Deleted {chord.label}.", 4000)

        def show_timeline_chord_status(self, chord: ChordRegion | None) -> None:
            if chord is None:
                return
            self.statusBar().showMessage(
                f"Selected {chord.label}: drag middle to move, drag edges to resize, Delete removes it.",
                6000,
            )

        def _merge_chord_ranges(self, ranges: list[tuple[float, float]]) -> list[tuple[float, float]]:
            valid = sorted((start, end) for start, end in ranges if end > start)
            merged: list[tuple[float, float]] = []
            for start, end in valid:
                if not merged or start > merged[-1][1]:
                    merged.append((start, end))
                else:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            return merged

        def refresh_visible_tracks(self) -> None:
            visible = {
                stem_name
                for stem_name, checkbox in self.track_visibility_checks.items()
                if checkbox.isChecked()
            }
            self.timeline.set_visible_tracks(visible)
            self.save_editor_state()

        def save_editor_state(self) -> None:
            if self.current_result is None or self.editor_project is None:
                return
            visibility = {}
            for stem_name, checkbox in self.track_visibility_checks.items():
                visibility[stem_name] = checkbox.isChecked()
            audio_enabled = {
                stem_name: checkbox.isChecked()
                for stem_name, checkbox in self.track_audio_checks.items()
            }
            audio_volume = {
                stem_name: slider.value()
                for stem_name, slider in self.track_audio_sliders.items()
            }
            midi_enabled = {
                stem_name: checkbox.isChecked()
                for stem_name, checkbox in self.track_midi_checks.items()
            }
            midi_volume = {
                stem_name: slider.value()
                for stem_name, slider in self.track_midi_sliders.items()
            }
            chord_overrides = [
                {
                    "start": chord.start,
                    "end": chord.end,
                    "label": chord.label,
                    "confidence": chord.confidence,
                }
                for chord in self.manual_chords
            ]
            chord_removals = [
                {"start": start, "end": end}
                for start, end in self.removed_chord_ranges
            ]
            save_project_manifest(
                self.current_result,
                track_visibility=visibility,
                track_audio_enabled=audio_enabled,
                track_audio_volume=audio_volume,
                track_midi_enabled=midi_enabled,
                track_midi_volume=midi_volume,
                playhead_seconds=self.timeline.position,
                chord_overrides=chord_overrides,
                chord_removals=chord_removals,
            )

        def reset_stage_state(self, _path: Path | None = None) -> None:
            self.stop_transport()
            if _path is None:
                self.drop_zone.reset_prompt()
            self.current_result = None
            self.current_stems = []
            self.current_input_stem = None
            self.editor_project = None
            self.manual_chords = []
            self.removed_chord_ranges = []
            self.clear_transport_players()
            self.track_audio_checks.clear()
            self.track_audio_sliders.clear()
            self.track_midi_checks.clear()
            self.track_midi_sliders.clear()
            self.run_midi.setEnabled(False)
            self.separation_status.setText("Not run yet.")
            self.midi_status.setText("Run the full pipeline first, then MIDI can be rerun without separating again.")
            self.editor_summary.setText("Run separation + MIDI to build an editor timeline.")
            self.timeline_slider.setRange(0, 0)
            self.timeline_slider.setEnabled(False)
            self.editor_position.setText(_format_time(0))
            self.current_chord.setText("Chord: -")
            self.chord_context.setText("Notes: -")
            self.track_list.clear()
            self.track_visibility_checks.clear()
            self.track_note_counts.clear()
            self.editor_track_visibility = {}
            _clear_layout(self.playback_controls)
            self.chord_list.clear()
            self.timeline.set_project(None)

        def set_processing_state(self, busy: bool) -> None:
            self.drop_zone.setEnabled(not busy)
            self.choose_output.setEnabled(not busy)
            self.run_full.setEnabled(not busy)
            self.run_midi.setEnabled((not busy) and self.current_result is not None)
            self.stem.setEnabled(not busy)
            self.bs_device.setEnabled(not busy)
            self.generate_midi.setEnabled(not busy)
            for checkbox in self.midi_stem_checks.values():
                checkbox.setEnabled(not busy and self.generate_midi.isChecked())
            for widget in [
                self.onset_threshold,
                self.frame_threshold,
                self.minimum_note_length,
                self.minimum_frequency,
                self.maximum_frequency,
                self.midi_tempo,
                self.melodia_trick,
                self.multiple_pitch_bends,
                self.save_notes,
                self.save_model_outputs,
                self.sonify_midi,
                self.sonification_samplerate,
                self.create_zip,
                self.open_when_done,
            ]:
                widget.setEnabled(not busy)
            if not busy:
                self.refresh_midi_stem_checks()

        def selected_model_key(self) -> str:
            return "bs_roformer_sw"

        def selected_separation_options(self) -> SeparationOptions:
            return SeparationOptions(
                model_key=self.selected_model_key(),
                selected_stem=self.stem.currentData(),
                device=self.bs_device.currentData(),
            )

        def selected_midi_options(self) -> MidiOptions:
            return MidiOptions(
                onset_threshold=self.onset_threshold.value(),
                frame_threshold=self.frame_threshold.value(),
                minimum_note_length=self.minimum_note_length.value(),
                minimum_frequency=_optional_frequency(self.minimum_frequency.value()),
                maximum_frequency=_optional_frequency(self.maximum_frequency.value()),
                multiple_pitch_bends=self.multiple_pitch_bends.isChecked(),
                melodia_trick=self.melodia_trick.isChecked(),
                midi_tempo=self.midi_tempo.value(),
                save_notes=self.save_notes.isChecked(),
                save_model_outputs=self.save_model_outputs.isChecked(),
                sonify_midi=self.sonify_midi.isChecked(),
                sonification_samplerate=self.sonification_samplerate.value(),
            )

        def selected_midi_stems(self) -> set[str]:
            if not self.generate_midi.isChecked():
                return set()
            return {
                stem_name
                for stem_name, checkbox in self.midi_stem_checks.items()
                if checkbox.isChecked()
            }

        def refresh_midi_stem_checks(self, *_args) -> None:
            choice = model_choice(self.selected_model_key())
            saved_stem = self.stem.currentData()
            previous = {stem: checkbox.isChecked() for stem, checkbox in self.midi_stem_checks.items()}
            self.midi_stem_checks.clear()
            _clear_layout(self.midi_stems_layout)

            for index, stem_name in enumerate(choice.stems):
                checkbox = QCheckBox(stem_name)
                checkbox.setChecked(previous.get(stem_name, _default_midi_checked(stem_name)))
                can_run = self.generate_midi.isChecked() and (saved_stem is None or stem_name == saved_stem)
                checkbox.setEnabled(can_run)
                if saved_stem is not None and stem_name != saved_stem:
                    checkbox.setChecked(False)
                    checkbox.setToolTip("This stem is not being saved, so it cannot be analysed.")
                elif stem_name.lower() == "drums":
                    checkbox.setToolTip("Off by default because Basic Pitch is not a drum transcription model.")
                else:
                    checkbox.setToolTip("Run Basic Pitch on this separated stem.")
                self.midi_stem_checks[stem_name] = checkbox
                self.midi_stems_layout.addWidget(checkbox, index // 2, index % 2)

        def refresh_model_details(self, *_args) -> None:
            choice = model_choice(self.selected_model_key())

            self.stem.blockSignals(True)
            self.stem.clear()
            self.stem.addItem("All stems from this model", None)
            for stem_name in choice.stems:
                self.stem.addItem(stem_name, stem_name)
            self.stem.blockSignals(False)
            self.refresh_midi_stem_checks()

            torch = torch_status()
            ort = onnxruntime_status()
            self.model_title.setText(choice.label)
            self.model_summary.setText(choice.summary)
            self.model_facts.setText(
                f"Best for: {choice.best_for}\n"
                f"Creates: {', '.join(choice.stems)}\n"
                f"Evidence: {choice.score_summary}"
            )
            self.model_runtime.setText(
                f"Separation: {choice.source} on {_device_label(self.bs_device.currentData(), torch.cuda_available)}. "
                f"MIDI: Spotify Basic Pitch ONNX on {'ONNX CUDA' if ort.has_cuda else 'ONNX CPU'}."
            )
            self.model_backend_detail.setText(
                f"BS-RoFormer: {choice.native_model_id}\n"
                f"Weights: {choice.filename or 'provided by registry'}\n"
                f"Config: {choice.config_filename or 'provided by registry'}\n"
                f"Calls: bs_roformer.inference.proc_folder -> basic_pitch.inference.predict_and_save"
            )

        def open_latest_output(self) -> None:
            target = self.latest_output_dir or Path(self.output_dir.text())
            target.mkdir(parents=True, exist_ok=True)
            os.startfile(target)

        def open_logs_folder(self) -> None:
            target = logs_dir()
            target.mkdir(parents=True, exist_ok=True)
            os.startfile(target)

    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("font-weight: 700; color: #374151; margin-top: 8px;")
        return label

    def _double_spin(low: float, high: float, value: float, step: float, decimals: int) -> QDoubleSpinBox:
        spin = NoWheelDoubleSpinBox()
        spin.setRange(low, high)
        spin.setValue(value)
        spin.setSingleStep(step)
        spin.setDecimals(decimals)
        return spin

    def _frequency_spin(special: str) -> QDoubleSpinBox:
        spin = _double_spin(0.0, 20000.0, 0.0, 10.0, 1)
        spin.setSpecialValueText(special)
        return spin

    def _optional_frequency(value: float) -> float | None:
        return value if value > 0 else None

    def _grid_control(layout: QGridLayout, row: int, column: int, label: str, default: str, widget: QWidget) -> None:
        stack = QVBoxLayout()
        stack.setSpacing(2)
        title = QLabel(label)
        title.setStyleSheet("font-weight: 600;")
        hint = QLabel(default)
        hint.setStyleSheet("color: #6b7280; font-size: 11px;")
        stack.addWidget(title)
        stack.addWidget(hint)
        stack.addWidget(widget)
        layout.addLayout(stack, row, column)

    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _default_midi_checked(stem_name: str) -> bool:
        return stem_name.lower() not in {"drums", "drum", "wet"}

    def _device_label(device: str | None, cuda_available: bool) -> str:
        if device == "cpu":
            return "PyTorch CPU (forced)"
        if device:
            return f"PyTorch CUDA ({device})"
        return "PyTorch CUDA (auto)" if cuda_available else "PyTorch CPU (auto fallback)"

    def _format_time(seconds: float) -> str:
        seconds = max(0.0, seconds)
        minutes = int(seconds // 60)
        remainder = seconds - (minutes * 60)
        return f"{minutes:02d}:{remainder:06.3f}"

    def _chord_preview_pitches(label: str, note_names: list[str]) -> list[int]:
        pitches = []
        previous = None
        for note_name in note_names:
            pitch_class = _pitch_class(note_name)
            pitch = 48 + pitch_class
            while previous is not None and pitch <= previous:
                pitch += 12
            pitches.append(pitch)
            previous = pitch
        if "/" in label:
            bass_name = label.split("/", 1)[1]
            bass_pitch = 36 + _pitch_class(bass_name)
            pitches.insert(0, bass_pitch)
        return pitches

    def _pitch_class(note_name: str) -> int:
        pitch_classes = {
            "C": 0,
            "C#": 1,
            "Db": 1,
            "D": 2,
            "D#": 3,
            "Eb": 3,
            "E": 4,
            "F": 5,
            "F#": 6,
            "Gb": 6,
            "G": 7,
            "G#": 8,
            "Ab": 8,
            "A": 9,
            "A#": 10,
            "Bb": 10,
            "B": 11,
        }
        return pitch_classes.get(note_name, 0)

    def _track_color(stem_name: str) -> QColor:
        palette = {
            "vocals": "#0ea5e9",
            "bass": "#22c55e",
            "guitar": "#f59e0b",
            "piano": "#8b5cf6",
            "other": "#64748b",
            "drums": "#ef4444",
            "instrumental": "#14b8a6",
        }
        return QColor(palette.get(stem_name.lower(), "#475569"))

    app = QApplication([])
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
