from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QSizePolicy,
)

from pitchstems.gui_note_map import _contrast_text_colour, _NoteMapWidget


class FretboardNoteMapWidget(_NoteMapWidget):
    tunings = {
        "bass": ("Bass", (28, 33, 38, 43), 20),
        "guitar": ("Guitar", (40, 45, 50, 55, 59, 64), 20),
    }

    def __init__(self) -> None:
        super().__init__("Selected notes", "No notes selected")
        self.tuning_key = "bass"
        self._note_hitboxes: list[tuple[QRectF, int, str]] = []
        self._fret_hitboxes: list[tuple[QRectF, int, str]] = []
        self.setMinimumHeight(118)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setToolTip("Shows every matching note position across the selected fretted instrument.")

    def set_tuning(self, tuning_key: str) -> None:
        if tuning_key in self.tunings:
            self.tuning_key = tuning_key
            self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        bounds = self.rect().adjusted(4, 4, -4, -4)
        painter.fillRect(bounds, QColor("#f8fafc"))
        painter.setPen(QPen(QColor("#cbd5e1"), 1))
        painter.drawRect(bounds)
        title_height = 18
        instrument_label, strings, fret_count = self.tunings[self.tuning_key]
        title = f"{self.source_label}: {self.chord_label}" if self.chord_label else self.source_label
        title = QFontMetrics(painter.font()).elidedText(
            f"{title} ({instrument_label})",
            Qt.ElideRight,
            max(0, bounds.width() - 12),
        )
        painter.setPen(QColor("#334155"))
        painter.drawText(bounds.left() + 6, bounds.top() + 1, max(0, bounds.width() - 12), title_height, Qt.AlignLeft | Qt.AlignVCenter, title)

        board = bounds.adjusted(8, title_height + 8, -8, -8)
        if board.width() <= 0 or board.height() <= 0:
            return
        string_count = len(strings)
        fret_width = board.width() / max(1, fret_count)
        string_gap = board.height() / max(1, string_count - 1)
        self._note_hitboxes = []
        self._fret_hitboxes = []

        painter.setPen(QPen(QColor("#94a3b8"), 1))
        for fret in range(fret_count + 1):
            x = board.left() + fret * fret_width
            pen_width = 3 if fret == 0 else 1
            painter.setPen(QPen(QColor("#475569" if fret == 0 else "#cbd5e1"), pen_width))
            painter.drawLine(round(x), round(board.top()), round(x), round(board.bottom()))
            if fret > 0 and fret in {3, 5, 7, 9, 12, 15, 17, 19}:
                painter.setPen(QColor("#64748b"))
                painter.drawText(QRectF(x - fret_width, board.bottom() - 13, fret_width, 12), Qt.AlignCenter, str(fret))

        self._draw_fret_markers(painter, board, fret_width, string_gap)

        for string_index, open_pitch in enumerate(reversed(strings)):
            y = board.top() + string_index * string_gap
            painter.setPen(QPen(QColor("#64748b"), 1 + string_index % 2))
            painter.drawLine(round(board.left()), round(y), round(board.right()), round(y))
            painter.setPen(QColor("#334155"))
            painter.drawText(
                QRectF(bounds.left() + 2, y - 8, 28, 16),
                Qt.AlignLeft | Qt.AlignVCenter,
                self.pitch_class_formatter(open_pitch % 12),
            )
            for fret in range(fret_count + 1):
                pitch = open_pitch + fret
                pitch_class = pitch % 12
                x = board.left() if fret == 0 else board.left() + (fret - 0.5) * fret_width
                name = self.pitch_class_formatter(pitch_class)
                hitbox_width = max(16, fret_width)
                hitbox_height = max(16, min(30, string_gap if string_count > 1 else board.height()))
                if fret == 0:
                    hitbox_left = max(bounds.left(), board.left() - hitbox_width * 0.5)
                else:
                    hitbox_left = board.left() + (fret - 1) * fret_width
                self._fret_hitboxes.append((QRectF(hitbox_left, y - hitbox_height * 0.5, hitbox_width, hitbox_height), pitch, name))
                if pitch_class not in self.pitch_classes:
                    continue
                radius = max(6, min(11, fret_width * 0.32))
                rect = QRectF(x - radius, y - radius, radius * 2, radius * 2)
                self._note_hitboxes.append((rect, pitch, name))
                painter.setPen(QPen(QColor("#92400e"), 1))
                fill_colour = QColor(self.note_colours.get(pitch_class, "#fde68a"))
                painter.setBrush(QBrush(fill_colour))
                painter.drawEllipse(rect)
                painter.setPen(_contrast_text_colour(fill_colour))
                painter.drawText(rect, Qt.AlignCenter, name[:2])
                self._draw_role_badge(painter, rect, pitch_class)
                self._draw_constraint_marker(painter, rect, pitch_class)

        if not self.pitch_classes:
            painter.setPen(QColor("#64748b"))
            painter.drawText(board, Qt.AlignCenter, self.empty_message)

    def mousePressEvent(self, event) -> None:
        hit = self._hit_note(event.position())
        if event.button() == Qt.RightButton and hit is not None:
            pitch, name = hit
            self._show_note_constraint_menu(event.globalPosition().toPoint(), pitch % 12, name)
            event.accept()
            return
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        if hit is not None:
            pitch, name = hit
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

    def _hit_note(self, position) -> tuple[int, str] | None:
        for rect, pitch, name in reversed(self._note_hitboxes):
            if rect.contains(position):
                return pitch, name
        for rect, pitch, name in reversed(self._fret_hitboxes):
            if rect.contains(position):
                return pitch, name
        return None

    def _draw_fret_markers(self, painter: QPainter, board: QRectF, fret_width: float, string_gap: float) -> None:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor("#cbd5e1")))
        radius = max(3.0, min(5.0, fret_width * 0.16))
        center_y = board.center().y()
        for fret in (3, 5, 7, 9, 12, 15, 17, 19):
            x = board.left() + (fret - 0.5) * fret_width
            if fret == 12:
                offset = max(10.0, string_gap * 0.7)
                painter.drawEllipse(QPointF(x, center_y - offset * 0.5), radius, radius)
                painter.drawEllipse(QPointF(x, center_y + offset * 0.5), radius, radius)
            else:
                painter.drawEllipse(QPointF(x, center_y), radius, radius)

    def _draw_role_badge(self, painter: QPainter, rect: QRectF, pitch_class: int) -> None:
        self._paint_role_badge(
            painter,
            pitch_class,
            lambda text: QRectF(rect.left() - 3, rect.top() - 8, max(14, len(text) * 8 + 5), 13),
        )

    def _draw_constraint_marker(self, painter: QPainter, rect: QRectF, pitch_class: int) -> None:
        color = self._constraint_colour(pitch_class)
        if color is None:
            return
        painter.setPen(QPen(color, 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(rect.adjusted(-2, -2, 2, 2))
