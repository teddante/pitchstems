from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QSizePolicy,
)

from pitchstems.gui_note_map import _contrast_text_colour, _NoteMapWidget
from pitchstems.notation import midi_note_name, midi_octave


class PianoChordWidget(_NoteMapWidget):
    black_pitch_classes = frozenset({1, 3, 6, 8, 10})
    black_key_offsets = {1: 0.72, 3: 0.72, 6: 0.72, 8: 0.72, 10: 0.72}

    def __init__(self) -> None:
        super().__init__("Selected chord", "No chord selected")
        self.preview_low_pitch = 48
        self.preview_high_pitch = 72
        self.on_preview_range_changed = None
        self._key_hitboxes: list[tuple[QRectF, int, str]] = []
        self._range_hitboxes: dict[str, QRectF] = {}
        self._range_rect = QRectF()
        self._dragging_range_bound: str | None = None
        self.setMinimumHeight(90)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMouseTracking(True)
        self.setToolTip("Select a chord candidate to see its tones on one octave of piano keys.")

    def set_preview_range(self, low_pitch: int, high_pitch: int) -> None:
        low, high = _normalized_preview_range(low_pitch, high_pitch)
        self.preview_low_pitch = low
        self.preview_high_pitch = high
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        bounds = self.rect().adjusted(4, 4, -4, -4)
        painter.fillRect(bounds, QColor("#f8fafc"))
        painter.setPen(QPen(QColor("#cbd5e1"), 1))
        painter.drawRect(bounds)

        title_height = 18
        range_height = 16
        title = f"{self.source_label}: {self.chord_label}" if self.chord_label else self.source_label
        title = QFontMetrics(painter.font()).elidedText(
            title,
            Qt.ElideRight,
            max(0, bounds.width() - 12),
        )
        painter.setPen(QColor("#334155"))
        painter.drawText(
            bounds.left() + 6,
            bounds.top() + 1,
            max(0, bounds.width() - 12),
            title_height,
            Qt.AlignLeft | Qt.AlignVCenter,
            title,
        )

        range_top = bounds.top() + title_height + 1
        range_rect = QRectF(bounds.left() + 6, range_top + 3, max(1, bounds.width() - 12), 6)
        self._draw_preview_range(painter, range_rect)

        keyboard_top = bounds.top() + title_height + range_height + 2
        keyboard_height = max(34, bounds.height() - title_height - range_height - 4)
        white_pitches = self._visible_white_pitches()
        white_width = max(1, bounds.width() / max(1, len(white_pitches)))
        self._key_hitboxes = []

        for index, pitch in enumerate(white_pitches):
            pitch_class = pitch % 12
            name = self._display_pitch_name(pitch, white_width)
            x = round(bounds.left() + index * white_width)
            next_x = round(bounds.left() + (index + 1) * white_width)
            width = max(1, next_x - x)
            self._key_hitboxes.append((QRectF(x, keyboard_top, width, keyboard_height), pitch, name))
            highlighted = pitch_class in self.pitch_classes
            fill_colour = self._highlight_colour(pitch_class, "#fde68a") if highlighted else QColor("#ffffff")
            painter.setBrush(QBrush(fill_colour))
            painter.setPen(QPen(QColor("#94a3b8"), 1))
            painter.drawRect(x, keyboard_top, width, keyboard_height)
            self._draw_constraint_marker(painter, QRectF(x, keyboard_top, width, keyboard_height), pitch_class)
            if highlighted:
                self._draw_role_badge(painter, QRectF(x, keyboard_top, width, keyboard_height), pitch_class)
            painter.setPen(_contrast_text_colour(fill_colour) if highlighted else QColor("#64748b"))
            if name:
                painter.drawText(
                    x,
                    keyboard_top + keyboard_height - 18,
                    width,
                    16,
                    Qt.AlignCenter,
                    name,
                )

        black_width = max(8, round(white_width * 0.56))
        black_height = round(keyboard_height * 0.62)
        white_index = {pitch: index for index, pitch in enumerate(white_pitches)}
        for pitch in self._visible_black_pitches():
            pitch_class = pitch % 12
            name = self._display_pitch_name(pitch, black_width)
            previous_white = self._previous_white_pitch(pitch)
            if previous_white not in white_index:
                continue
            center_position = white_index[previous_white] + self.black_key_offsets[pitch_class]
            center_x = bounds.left() + center_position * white_width
            x = round(center_x - black_width / 2)
            self._key_hitboxes.append((QRectF(x, keyboard_top, black_width, black_height), pitch, name))
            highlighted = pitch_class in self.pitch_classes
            fill_colour = self._highlight_colour(pitch_class, "#fbbf24") if highlighted else QColor("#111827")
            painter.setBrush(QBrush(fill_colour))
            painter.setPen(QPen(QColor("#475569" if highlighted else "#020617"), 1))
            painter.drawRect(x, keyboard_top, black_width, black_height)
            self._draw_constraint_marker(painter, QRectF(x, keyboard_top, black_width, black_height), pitch_class)
            if highlighted:
                self._draw_role_badge(painter, QRectF(x, keyboard_top, black_width, black_height), pitch_class)
            if name:
                painter.setPen(_contrast_text_colour(fill_colour) if highlighted else QColor("#f8fafc"))
                painter.drawText(x, keyboard_top + black_height - 16, black_width, 14, Qt.AlignCenter, name)

        if not self.pitch_classes:
            painter.setPen(QColor("#64748b"))
            painter.drawText(
                bounds.left(),
                keyboard_top,
                bounds.width(),
                keyboard_height,
                Qt.AlignCenter,
                self.empty_message,
            )

    def _role_tooltip_text(self) -> str:
        labels = []
        for pitch_class, roles in sorted(self.note_roles.items()):
            role_text = "/".join(sorted(roles))
            note_name = self.pitch_class_formatter(pitch_class)
            labels.append(f"{role_text} {note_name}")
        return ", ".join(labels)

    def _tooltip_suffix(self) -> str:
        voicing = self._role_tooltip_text()
        return f"\nVoicing: {voicing}" if voicing else ""

    def _visible_white_pitches(self) -> list[int]:
        low = self._previous_white_pitch(self.preview_low_pitch)
        high = self._next_white_pitch(self.preview_high_pitch)
        return [
            pitch
            for pitch in range(low, high + 1)
            if pitch % 12 not in self.black_pitch_classes
        ]

    def _visible_black_pitches(self) -> list[int]:
        low = self._previous_white_pitch(self.preview_low_pitch)
        high = self._next_white_pitch(self.preview_high_pitch)
        return [
            pitch
            for pitch in range(low, high + 1)
            if pitch % 12 in self.black_pitch_classes
        ]

    def _previous_white_pitch(self, pitch: int) -> int:
        while pitch % 12 in self.black_pitch_classes:
            pitch -= 1
        return pitch

    def _next_white_pitch(self, pitch: int) -> int:
        while pitch % 12 in self.black_pitch_classes:
            pitch += 1
        return pitch

    def _display_pitch_name(self, pitch: int, key_width: float) -> str:
        name = self.pitch_class_formatter(pitch % 12)
        metrics = QFontMetrics(self.font())
        full = f"{name}{midi_octave(pitch)}"
        if key_width >= 22 and metrics.horizontalAdvance(full) <= key_width:
            return full
        if metrics.horizontalAdvance(name) <= key_width:
            return name
        return ""

    def _draw_role_badge(self, painter: QPainter, rect: QRectF, pitch_class: int) -> None:
        self._paint_role_badge(
            painter,
            pitch_class,
            lambda text: QRectF(
                rect.left() + 2,
                rect.top() + 2,
                min(max(14, len(text) * 8 + 6), max(14, int(rect.width()) - 4)),
                14,
            ),
        )

    def _draw_constraint_marker(self, painter: QPainter, rect: QRectF, pitch_class: int) -> None:
        color = self._constraint_colour(pitch_class)
        if color is None:
            return
        state = self.note_constraints[pitch_class]
        painter.setPen(QPen(color, 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect.adjusted(2, 2, -2, -2))
        badge = QRectF(rect.right() - 16, rect.top() + 2, 14, 14)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawRoundedRect(badge, 3, 3)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(badge, Qt.AlignCenter, "+" if state == "force" else "-")

    def _draw_preview_range(self, painter: QPainter, rect: QRectF) -> None:
        self._range_rect = QRectF(rect)
        painter.setPen(QPen(QColor("#cbd5e1"), 1))
        painter.setBrush(QBrush(QColor("#e2e8f0")))
        painter.drawRoundedRect(rect, 3, 3)
        low_x = self._range_x(self.preview_low_pitch, rect)
        high_x = self._range_x(self.preview_high_pitch, rect)
        selected = QRectF(min(low_x, high_x), rect.top(), max(2, abs(high_x - low_x)), rect.height())
        painter.setBrush(QBrush(QColor("#93c5fd")))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(selected, 3, 3)
        self._range_hitboxes = {}
        for bound, x in (("low", low_x), ("high", high_x)):
            handle = QRectF(x - 4, rect.top() - 4, 8, rect.height() + 8)
            self._range_hitboxes[bound] = handle
            painter.setBrush(QBrush(QColor("#2563eb")))
            painter.setPen(QPen(QColor("#1e3a8a"), 1))
            painter.drawRoundedRect(handle, 3, 3)
        label = f"{midi_note_name(self.preview_low_pitch)} - {midi_note_name(self.preview_high_pitch)}"
        label_width = max(0, int(selected.width()) - 24)
        metrics = QFontMetrics(self.font())
        if label_width >= metrics.horizontalAdvance(label):
            painter.setPen(QColor("#334155"))
            painter.drawText(QRectF(selected.left() + 12, rect.top() - 6, label_width, rect.height() + 14), Qt.AlignCenter, label)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.RightButton:
            for rect, pitch, name in reversed(self._key_hitboxes):
                if rect.contains(event.position()):
                    self._show_note_constraint_menu(event.globalPosition().toPoint(), pitch % 12, name)
                    event.accept()
                    return
        if event.button() == Qt.LeftButton:
            for bound, rect in self._range_hitboxes.items():
                if rect.contains(event.position()):
                    self._dragging_range_bound = bound
                    self._set_preview_range_from_position(bound, event.position().x())
                    event.accept()
                    return
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        for rect, pitch, name in reversed(self._key_hitboxes):
            if rect.contains(event.position()):
                modifiers = event.modifiers() if hasattr(event, "modifiers") else Qt.NoModifier
                if modifiers & Qt.ControlModifier:
                    self._cycle_note_constraint(pitch % 12)
                elif self.on_note_clicked is not None:
                    self.on_note_clicked(pitch, name)
                else:
                    super().mousePressEvent(event)
                    return
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging_range_bound is None:
            super().mouseMoveEvent(event)
            return
        self._set_preview_range_from_position(self._dragging_range_bound, event.position().x())
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if self._dragging_range_bound is not None:
            self._dragging_range_bound = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _set_preview_range_from_position(self, bound: str, x: float) -> None:
        pitch = self._pitch_for_range_x(x)
        if bound == "low":
            low, high = _normalized_preview_range(pitch, self.preview_high_pitch)
        else:
            low, high = _normalized_preview_range(self.preview_low_pitch, pitch)
        if (low, high) == (self.preview_low_pitch, self.preview_high_pitch):
            return
        self.preview_low_pitch = low
        self.preview_high_pitch = high
        if self.on_preview_range_changed is not None:
            self.on_preview_range_changed(low, high)
        self.update()

    def _range_x(self, pitch: int, rect: QRectF) -> float:
        minimum, maximum = 36, 84
        clamped = min(maximum, max(minimum, pitch))
        return rect.left() + ((clamped - minimum) / (maximum - minimum)) * rect.width()

    def _pitch_for_range_x(self, x: float) -> int:
        if self._range_rect.isNull():
            return self.preview_low_pitch
        left = self._range_rect.left()
        right = self._range_rect.right()
        width = max(1.0, right - left)
        ratio = min(1.0, max(0.0, (x - left) / width))
        return round(36 + ratio * (84 - 36))


def _normalized_preview_range(low_pitch: int, high_pitch: int) -> tuple[int, int]:
    low = min(84, max(36, int(low_pitch)))
    high = min(84, max(36, int(high_pitch)))
    if high < low:
        low, high = high, low
    if high - low < 1:
        high = min(84, low + 1)
        low = max(36, high - 1)
    return low, high
