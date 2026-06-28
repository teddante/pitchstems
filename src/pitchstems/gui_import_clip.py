from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from pitchstems.audio import AudioWaveformPreview, load_waveform_preview
from pitchstems.audio_clip import MIN_CLIP_SECONDS, AudioClipRange, clamp_clip_range
from pitchstems.time_format import format_time


class ImportClipPicker(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.path: Path | None = None
        self.duration_seconds = 0.0
        self.peaks: tuple[float, ...] = ()
        self.clip_range: AudioClipRange | None = None
        self.on_range_changed = None
        self._cache: dict[Path, AudioWaveformPreview] = {}
        self._drag_anchor: float | None = None
        self.setMinimumHeight(84)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)
        self.setEnabled(False)
        self.setToolTip("Drag across the waveform to process only that part of the audio.")

    def set_audio_file(self, path: Path, log=None) -> None:
        self.path = path
        self.clip_range = None
        self._drag_anchor = None
        try:
            preview = self._cache.get(path)
            if preview is None:
                preview = load_waveform_preview(path)
                self._cache[path] = preview
            self.duration_seconds = preview.duration_seconds
            self.peaks = preview.peaks
            self.setEnabled(self.duration_seconds > 0)
        except Exception as exc:
            self.duration_seconds = 0.0
            self.peaks = ()
            self.setEnabled(False)
            if log is not None:
                log(f"Waveform preview unavailable: {exc}")
        self._notify()
        self.update()

    def reset_audio(self) -> None:
        self.path = None
        self.duration_seconds = 0.0
        self.peaks = ()
        self.clip_range = None
        self._drag_anchor = None
        self.setEnabled(False)
        self._notify()
        self.update()

    def selected_clip_range(self) -> AudioClipRange | None:
        return self.clip_range

    def clear_selection(self) -> None:
        self.clip_range = None
        self._drag_anchor = None
        self._notify()
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton or self.duration_seconds <= 0:
            return
        seconds = self._seconds_at(event.position().x())
        self._drag_anchor = seconds
        self.clip_range = None
        self._notify()
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_anchor is None or self.duration_seconds <= 0:
            return
        self.clip_range = clamp_clip_range(
            self._drag_anchor,
            self._seconds_at(event.position().x()),
            self.duration_seconds,
        )
        self._notify()
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.LeftButton or self._drag_anchor is None:
            return
        self.clip_range = clamp_clip_range(
            self._drag_anchor,
            self._seconds_at(event.position().x()),
            self.duration_seconds,
        )
        self._drag_anchor = None
        self._notify()
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        bounds = self.rect().adjusted(4, 8, -4, -8)
        painter.fillRect(bounds, QColor("#f8fafc"))
        painter.setPen(QPen(QColor("#cbd5e1"), 1))
        painter.drawRoundedRect(bounds, 6, 6)

        mid_y = bounds.center().y()
        painter.setPen(QPen(QColor("#94a3b8"), 1))
        painter.drawLine(bounds.left() + 4, mid_y, bounds.right() - 4, mid_y)

        if self.peaks:
            width = max(1, bounds.width() - 12)
            x0 = bounds.left() + 6
            painter.setPen(QPen(QColor("#2563eb"), 1))
            for index, peak in enumerate(self.peaks):
                x = x0 + round(index * width / max(1, len(self.peaks) - 1))
                half_height = max(1, round(peak * (bounds.height() * 0.42)))
                painter.drawLine(x, mid_y - half_height, x, mid_y + half_height)

        if self.clip_range is not None:
            start_x = self._x_at(self.clip_range.start_seconds)
            end_x = self._x_at(self.clip_range.end_seconds)
            selection = bounds.adjusted(0, 1, 0, -1)
            selection.setLeft(round(start_x))
            selection.setRight(round(end_x))
            painter.fillRect(selection, QColor(59, 130, 246, 58))
            painter.setPen(QPen(QColor("#1d4ed8"), 2))
            painter.drawLine(round(start_x), bounds.top() + 2, round(start_x), bounds.bottom() - 2)
            painter.drawLine(round(end_x), bounds.top() + 2, round(end_x), bounds.bottom() - 2)

    def _seconds_at(self, x: float) -> float:
        bounds = self.rect().adjusted(4, 8, -4, -8)
        ratio = (x - bounds.left()) / max(1, bounds.width())
        return max(0.0, min(self.duration_seconds, ratio * self.duration_seconds))

    def _x_at(self, seconds: float) -> float:
        bounds = self.rect().adjusted(4, 8, -4, -8)
        ratio = max(0.0, min(seconds, self.duration_seconds)) / max(self.duration_seconds, 0.001)
        return bounds.left() + ratio * bounds.width()

    def _notify(self) -> None:
        if self.on_range_changed:
            self.on_range_changed(self.clip_range, self.duration_seconds)


def clip_status_text(clip_range: AudioClipRange | None, duration_seconds: float) -> str:
    if duration_seconds <= 0:
        return "Whole file"
    if clip_range is None:
        return f"Whole file: {format_time(duration_seconds)}"
    return (
        f"Clip: {format_time(clip_range.start_seconds)} - "
        f"{format_time(clip_range.end_seconds)} "
        f"({format_time(clip_range.duration_seconds)})"
    )


def import_preview_range(
    clip_range: AudioClipRange | None,
    duration_seconds: float,
) -> tuple[float, float] | None:
    duration = max(0.0, duration_seconds)
    if clip_range is not None:
        return clip_range.start_seconds, clip_range.end_seconds
    if duration < MIN_CLIP_SECONDS:
        return None
    return 0.0, duration
