from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QBrush, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QMenu,
    QComboBox,
    QDoubleSpinBox,
    QLabel,
    QSizePolicy,
    QSpinBox,
    QWidget,
)

from pitchstems.input_validation import validate_audio_input
from pitchstems.notation import pitch_class_for_name, pitch_class_name


class DropZone(QLabel):
    def __init__(self) -> None:
        super().__init__("Drop an audio file here")
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
        self.setMinimumHeight(96)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
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
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if not urls or not urls[0].isLocalFile():
            return
        path = Path(urls[0].toLocalFile())
        error = validate_audio_input(path)
        if error:
            self.path = None
            self.setText(error)
            self.setToolTip(error)
            if self.on_path_changed:
                self.on_path_changed(None)
            return
        self.set_audio_file(path)
        if self.on_path_changed:
            self.on_path_changed(self.path)


class _NoWheelMixin:
    def wheelEvent(self, event) -> None:
        event.ignore()


class NoWheelComboBox(_NoWheelMixin, QComboBox):
    pass


class NoWheelDoubleSpinBox(_NoWheelMixin, QDoubleSpinBox):
    pass


class NoWheelSpinBox(_NoWheelMixin, QSpinBox):
    pass


class PianoChordWidget(QWidget):
    black_pitch_classes = {1, 3, 6, 8, 10}
    black_key_offsets = {1: 0.72, 3: 0.72, 6: 0.72, 8: 0.72, 10: 0.72}

    def __init__(self) -> None:
        super().__init__()
        self.chord_label = ""
        self.source_label = "Selected chord"
        self.empty_message = "No chord selected"
        self.pitch_classes: set[int] = set()
        self.note_roles: dict[int, set[str]] = {}
        self.note_constraints: dict[int, str] = {}
        self.note_colours: dict[int, str] = {}
        self.preview_low_pitch = 48
        self.preview_high_pitch = 72
        self.pitch_class_formatter = pitch_class_name
        self.on_note_clicked = None
        self.on_note_constraint_changed = None
        self.on_note_constraints_reset = None
        self.on_preview_range_changed = None
        self._key_hitboxes: list[tuple[QRectF, int, str]] = []
        self._range_hitboxes: dict[str, QRectF] = {}
        self._range_rect = QRectF()
        self._dragging_range_bound: str | None = None
        self.setMinimumHeight(90)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMouseTracking(True)
        self.setToolTip("Select a chord candidate to see its tones on one octave of piano keys.")

    def set_pitch_class_formatter(self, formatter) -> None:
        self.pitch_class_formatter = formatter
        self.update()

    def set_chord(
        self,
        label: str | None,
        note_names: list[str],
        source_label: str = "Selected chord",
        note_roles: dict[int, set[str]] | None = None,
    ) -> None:
        self.set_notes(label, note_names, source_label, note_roles, empty_message="No chord selected")

    def set_notes(
        self,
        label: str | None,
        note_names: list[str],
        source_label: str = "Selected notes",
        note_roles: dict[int, set[str]] | None = None,
        empty_message: str = "No notes selected",
    ) -> None:
        self.chord_label = label or ""
        self.source_label = source_label
        self.empty_message = empty_message
        self.pitch_classes = {
            pitch_class
            for note_name in note_names
            for pitch_class in [pitch_class_for_name(note_name)]
            if pitch_class is not None
        }
        self.note_roles = {
            pitch_class % 12: set(roles)
            for pitch_class, roles in (note_roles or {}).items()
            if roles
        }
        if self.chord_label and self.pitch_classes:
            tones = " - ".join(note_names)
            voicing = self._role_tooltip_text()
            suffix = f"\nVoicing: {voicing}" if voicing else ""
            self.setToolTip(f"{self.source_label}: {self.chord_label}\n{tones}{suffix}")
        else:
            self.setToolTip(self.empty_message)
        self.update()

    def set_note_constraints(self, constraints: dict[int, str] | None) -> None:
        self.note_constraints = {
            pitch_class % 12: state
            for pitch_class, state in (constraints or {}).items()
            if state in {"force", "exclude"}
        }
        self.update()

    def set_note_colours(self, colours: dict[int, str] | None) -> None:
        self.note_colours = {
            pitch_class % 12: colour
            for pitch_class, colour in (colours or {}).items()
            if colour
        }
        self.update()

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
            name = self._display_pitch_name(pitch, white_width)
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
        if key_width >= 22:
            return f"{name}{pitch // 12 - 1}"
        return name

    def _highlight_colour(self, pitch_class: int, fallback: str) -> QColor:
        return QColor(self.note_colours.get(pitch_class, fallback))

    def _draw_role_badge(self, painter: QPainter, rect: QRectF, pitch_class: int) -> None:
        roles = self.note_roles.get(pitch_class)
        if not roles:
            return
        text = "/".join(role[:1].upper() for role in sorted(roles))
        badge_width = min(max(14, len(text) * 8 + 6), max(14, int(rect.width()) - 4))
        badge = QRectF(rect.left() + 2, rect.top() + 2, badge_width, 14)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor("#0f766e")))
        painter.drawRoundedRect(badge, 3, 3)
        painter.setPen(QColor("#f8fafc"))
        painter.drawText(badge, Qt.AlignCenter, text)

    def _draw_constraint_marker(self, painter: QPainter, rect: QRectF, pitch_class: int) -> None:
        state = self.note_constraints.get(pitch_class)
        if state not in {"force", "exclude"}:
            return
        color = QColor("#16a34a" if state == "force" else "#dc2626")
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
        label = f"{pitch_class_name(self.preview_low_pitch % 12)}{self.preview_low_pitch // 12 - 1}"
        label += f" - {pitch_class_name(self.preview_high_pitch % 12)}{self.preview_high_pitch // 12 - 1}"
        painter.setPen(QColor("#334155"))
        painter.drawText(rect.adjusted(6, -6, -6, 8), Qt.AlignCenter, label)

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

    def _show_note_constraint_menu(self, position, pitch_class: int, name: str) -> None:
        menu = QMenu(self)
        actions = {
            "auto": menu.addAction(f"Auto {name}"),
            "force": menu.addAction(f"Force include {name}"),
            "exclude": menu.addAction(f"Force exclude {name}"),
        }
        menu.addSeparator()
        clear_action = menu.addAction("Clear forced notes")
        selected = menu.exec(position)
        if selected == clear_action:
            if self.on_note_constraints_reset is not None:
                self.on_note_constraints_reset()
            return
        for state, action in actions.items():
            if selected == action:
                self._set_note_constraint(pitch_class, state)
                return

    def _cycle_note_constraint(self, pitch_class: int) -> None:
        state = self.note_constraints.get(pitch_class, "auto")
        next_state = {"auto": "force", "force": "exclude", "exclude": "auto"}[state]
        self._set_note_constraint(pitch_class, next_state)

    def _set_note_constraint(self, pitch_class: int, state: str) -> None:
        pitch_class %= 12
        if state == "auto":
            self.note_constraints.pop(pitch_class, None)
        elif state in {"force", "exclude"}:
            self.note_constraints[pitch_class] = state
        if self.on_note_constraint_changed is not None:
            self.on_note_constraint_changed(pitch_class, state)
        self.update()

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
        return int(round(36 + ratio * (84 - 36)))


def _normalized_preview_range(low_pitch: int, high_pitch: int) -> tuple[int, int]:
    low = min(84, max(36, int(low_pitch)))
    high = min(84, max(36, int(high_pitch)))
    if high < low:
        low, high = high, low
    if high - low < 1:
        high = min(84, low + 1)
        low = max(36, high - 1)
    return low, high


class FretboardNoteMapWidget(QWidget):
    tunings = {
        "bass": ("Bass", (28, 33, 38, 43), 20),
        "guitar": ("Guitar", (40, 45, 50, 55, 59, 64), 20),
    }

    def __init__(self) -> None:
        super().__init__()
        self.chord_label = ""
        self.source_label = "Selected notes"
        self.empty_message = "No notes selected"
        self.pitch_classes: set[int] = set()
        self.note_roles: dict[int, set[str]] = {}
        self.note_constraints: dict[int, str] = {}
        self.note_colours: dict[int, str] = {}
        self.pitch_class_formatter = pitch_class_name
        self.tuning_key = "bass"
        self.on_note_clicked = None
        self.on_note_constraint_changed = None
        self.on_note_constraints_reset = None
        self._note_hitboxes: list[tuple[QRectF, int, str]] = []
        self._fret_hitboxes: list[tuple[QRectF, int, str]] = []
        self.setMinimumHeight(118)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setToolTip("Shows every matching note position across the selected fretted instrument.")

    def set_tuning(self, tuning_key: str) -> None:
        if tuning_key in self.tunings:
            self.tuning_key = tuning_key
            self.update()

    def set_pitch_class_formatter(self, formatter) -> None:
        self.pitch_class_formatter = formatter
        self.update()

    def set_chord(
        self,
        label: str | None,
        note_names: list[str],
        source_label: str = "Selected chord",
        note_roles: dict[int, set[str]] | None = None,
    ) -> None:
        self.set_notes(label, note_names, source_label, note_roles, empty_message="No chord selected")

    def set_notes(
        self,
        label: str | None,
        note_names: list[str],
        source_label: str = "Selected notes",
        note_roles: dict[int, set[str]] | None = None,
        empty_message: str = "No notes selected",
    ) -> None:
        self.chord_label = label or ""
        self.source_label = source_label
        self.empty_message = empty_message
        self.pitch_classes = {
            pitch_class
            for note_name in note_names
            for pitch_class in [pitch_class_for_name(note_name)]
            if pitch_class is not None
        }
        self.note_roles = {
            pitch_class % 12: set(roles)
            for pitch_class, roles in (note_roles or {}).items()
            if roles
        }
        if self.chord_label and self.pitch_classes:
            tones = " - ".join(note_names)
            self.setToolTip(f"{self.source_label}: {self.chord_label}\n{tones}")
        else:
            self.setToolTip(self.empty_message)
        self.update()

    def set_note_constraints(self, constraints: dict[int, str] | None) -> None:
        self.note_constraints = {
            pitch_class % 12: state
            for pitch_class, state in (constraints or {}).items()
            if state in {"force", "exclude"}
        }
        self.update()

    def set_note_colours(self, colours: dict[int, str] | None) -> None:
        self.note_colours = {
            pitch_class % 12: colour
            for pitch_class, colour in (colours or {}).items()
            if colour
        }
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
        if event.button() == Qt.RightButton:
            if hit is not None:
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
        roles = self.note_roles.get(pitch_class)
        if not roles:
            return
        text = "/".join(role[:1].upper() for role in sorted(roles))
        badge = QRectF(rect.left() - 3, rect.top() - 8, max(14, len(text) * 8 + 5), 13)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor("#0f766e")))
        painter.drawRoundedRect(badge, 3, 3)
        painter.setPen(QColor("#f8fafc"))
        painter.drawText(badge, Qt.AlignCenter, text)

    def _draw_constraint_marker(self, painter: QPainter, rect: QRectF, pitch_class: int) -> None:
        state = self.note_constraints.get(pitch_class)
        if state not in {"force", "exclude"}:
            return
        color = QColor("#16a34a" if state == "force" else "#dc2626")
        painter.setPen(QPen(color, 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(rect.adjusted(-2, -2, 2, 2))

    def _show_note_constraint_menu(self, position, pitch_class: int, name: str) -> None:
        menu = QMenu(self)
        actions = {
            "auto": menu.addAction(f"Auto {name}"),
            "force": menu.addAction(f"Force include {name}"),
            "exclude": menu.addAction(f"Force exclude {name}"),
        }
        menu.addSeparator()
        clear_action = menu.addAction("Clear forced notes")
        selected = menu.exec(position)
        if selected == clear_action:
            if self.on_note_constraints_reset is not None:
                self.on_note_constraints_reset()
            return
        for state, action in actions.items():
            if selected == action:
                self._set_note_constraint(pitch_class, state)
                return

    def _cycle_note_constraint(self, pitch_class: int) -> None:
        state = self.note_constraints.get(pitch_class, "auto")
        next_state = {"auto": "force", "force": "exclude", "exclude": "auto"}[state]
        self._set_note_constraint(pitch_class, next_state)

    def _set_note_constraint(self, pitch_class: int, state: str) -> None:
        pitch_class %= 12
        if state == "auto":
            self.note_constraints.pop(pitch_class, None)
        elif state in {"force", "exclude"}:
            self.note_constraints[pitch_class] = state
        if self.on_note_constraint_changed is not None:
            self.on_note_constraint_changed(pitch_class, state)
        self.update()


def _contrast_text_colour(colour: QColor) -> QColor:
    luminance = (colour.red() * 0.299) + (colour.green() * 0.587) + (colour.blue() * 0.114)
    return QColor("#111827" if luminance > 150 else "#f8fafc")
