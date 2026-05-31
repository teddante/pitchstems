from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QLabel,
    QSizePolicy,
    QSpinBox,
    QWidget,
)

from pitchstems.notation import pitch_class_for_name


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


class PianoChordWidget(QWidget):
    white_keys = [
        ("C", 0),
        ("D", 2),
        ("E", 4),
        ("F", 5),
        ("G", 7),
        ("A", 9),
        ("B", 11),
        ("C", 0),
    ]
    black_keys = [
        ("C#", 1, 0.72),
        ("Eb", 3, 1.72),
        ("F#", 6, 3.72),
        ("Ab", 8, 4.72),
        ("Bb", 10, 5.72),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.chord_label = ""
        self.source_label = "Selected chord"
        self.pitch_classes: set[int] = set()
        self.setMinimumHeight(90)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setToolTip("Select a chord candidate to see its tones on one octave of piano keys.")

    def set_chord(
        self,
        label: str | None,
        note_names: list[str],
        source_label: str = "Selected chord",
    ) -> None:
        self.chord_label = label or ""
        self.source_label = source_label
        self.pitch_classes = {
            pitch_class
            for note_name in note_names
            for pitch_class in [pitch_class_for_name(note_name)]
            if pitch_class is not None
        }
        if self.chord_label and self.pitch_classes:
            tones = " - ".join(note_names)
            self.setToolTip(f"{self.source_label}: {self.chord_label}\n{tones}")
        else:
            self.setToolTip("Select a chord candidate to see its tones on one octave of piano keys.")
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        bounds = self.rect().adjusted(4, 4, -4, -4)
        painter.fillRect(bounds, QColor("#f8fafc"))
        painter.setPen(QPen(QColor("#cbd5e1"), 1))
        painter.drawRect(bounds)

        title_height = 18
        title = f"{self.source_label}: {self.chord_label}" if self.chord_label else "Selected chord"
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

        keyboard_top = bounds.top() + title_height + 2
        keyboard_height = max(34, bounds.height() - title_height - 4)
        white_width = max(1, bounds.width() / len(self.white_keys))

        for index, (name, pitch_class) in enumerate(self.white_keys):
            x = round(bounds.left() + index * white_width)
            next_x = round(bounds.left() + (index + 1) * white_width)
            width = max(1, next_x - x)
            highlighted = pitch_class in self.pitch_classes
            painter.setBrush(QBrush(QColor("#fde68a" if highlighted else "#ffffff")))
            painter.setPen(QPen(QColor("#94a3b8"), 1))
            painter.drawRect(x, keyboard_top, width, keyboard_height)
            painter.setPen(QColor("#1f2937" if highlighted else "#64748b"))
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
        for name, pitch_class, center_position in self.black_keys:
            center_x = bounds.left() + center_position * white_width
            x = round(center_x - black_width / 2)
            highlighted = pitch_class in self.pitch_classes
            painter.setBrush(QBrush(QColor("#fbbf24" if highlighted else "#111827")))
            painter.setPen(QPen(QColor("#475569" if highlighted else "#020617"), 1))
            painter.drawRect(x, keyboard_top, black_width, black_height)
            painter.setPen(QColor("#111827" if highlighted else "#f8fafc"))
            painter.drawText(x, keyboard_top + black_height - 16, black_width, 14, Qt.AlignCenter, name)

        if not self.pitch_classes:
            painter.setPen(QColor("#64748b"))
            painter.drawText(
                bounds.left(),
                keyboard_top,
                bounds.width(),
                keyboard_height,
                Qt.AlignCenter,
                "No chord selected",
            )
