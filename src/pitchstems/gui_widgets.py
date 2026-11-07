from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QLabel,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
)

from pitchstems.gui_fretboard_widget import FretboardNoteMapWidget
from pitchstems.gui_note_map import _NoteMapWidget
from pitchstems.gui_piano_widget import PianoChordWidget
from pitchstems.input_validation import validate_audio_input
from pitchstems.recent_projects import short_path


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
        self.setText(f"Audio\n{path.name}\n{short_path(path.parent, 72)}")
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

    def show_error(self, error: str) -> None:
        self.path = None
        self.setText(error)
        self.setToolTip(error)

    def reset_prompt(self) -> None:
        self.path = None
        self.setText("Drop an audio file here")
        self.setToolTip("")

    def dragEnterEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if not urls or not urls[0].isLocalFile():
            return
        path = Path(urls[0].toLocalFile())
        if self.on_path_changed:
            # The window validates the drop and resets the clip picker and
            # project state for both valid and invalid files.
            self.on_path_changed(path)
            return
        error = validate_audio_input(path)
        if error:
            self.show_error(error)
            return
        self.set_audio_file(path)


class _NoWheelMixin:
    def wheelEvent(self, event) -> None:
        event.ignore()


class NoWheelComboBox(_NoWheelMixin, QComboBox):
    pass


class NoWheelDoubleSpinBox(_NoWheelMixin, QDoubleSpinBox):
    pass


class NoWheelSpinBox(_NoWheelMixin, QSpinBox):
    pass


class NoteMapPair:
    """Piano and bass/guitar views of the same notes, switched by a view-mode combo box."""

    def __init__(
        self,
        *,
        pitch_class_formatter,
        on_note_clicked,
        on_note_constraint_changed,
        on_note_constraints_reset,
        on_preview_range_changed,
        preview_range: tuple[int, int],
        mode_tooltip: str,
    ) -> None:
        self.piano = PianoChordWidget()
        self.fretboard = FretboardNoteMapWidget()
        for view in self.views:
            view.set_pitch_class_formatter(pitch_class_formatter)
            view.on_note_clicked = on_note_clicked
            view.on_note_constraint_changed = on_note_constraint_changed
            view.on_note_constraints_reset = on_note_constraints_reset
        self.piano.on_preview_range_changed = on_preview_range_changed
        self.piano.set_preview_range(*preview_range)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.piano)
        self.stack.addWidget(self.fretboard)
        self.mode = NoWheelComboBox()
        self.mode.addItem("Piano", "piano")
        self.mode.addItem("Bass", "bass")
        self.mode.addItem("Guitar", "guitar")
        self.mode.setToolTip(mode_tooltip)
        self.mode.currentIndexChanged.connect(self._apply_mode)

    @property
    def views(self) -> tuple[_NoteMapWidget, ...]:
        return (self.piano, self.fretboard)

    def set_chord(self, *args, **kwargs) -> None:
        for view in self.views:
            view.set_chord(*args, **kwargs)

    def set_notes(self, *args, **kwargs) -> None:
        for view in self.views:
            view.set_notes(*args, **kwargs)

    def set_note_constraints(self, constraints: dict[int, str] | None) -> None:
        for view in self.views:
            view.set_note_constraints(constraints)

    def set_note_colours(self, colours: dict[int, str] | None) -> None:
        for view in self.views:
            view.set_note_colours(colours)

    def set_pitch_class_formatter(self, formatter) -> None:
        for view in self.views:
            view.set_pitch_class_formatter(formatter)

    def set_preview_range(self, low_pitch: int, high_pitch: int) -> None:
        self.piano.set_preview_range(low_pitch, high_pitch)

    def _apply_mode(self, *_args) -> None:
        mode = self.mode.currentData() or "piano"
        self.stack.setCurrentWidget(self.piano if mode == "piano" else self.fretboard)
        if mode in {"bass", "guitar"}:
            self.fretboard.set_tuning(mode)
