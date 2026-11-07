from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPainter
from PySide6.QtWidgets import (
    QMenu,
    QWidget,
)

from pitchstems.harmony_inspector import apply_note_override
from pitchstems.notation import pitch_class_for_name, pitch_class_name


class _NoteMapWidget(QWidget):
    def __init__(self, source_label: str, empty_message: str) -> None:
        super().__init__()
        self.chord_label = ""
        self.source_label = source_label
        self.empty_message = empty_message
        self.pitch_classes: set[int] = set()
        self.note_roles: dict[int, set[str]] = {}
        self.note_constraints: dict[int, str] = {}
        self.note_colours: dict[int, str] = {}
        self.pitch_class_formatter = pitch_class_name
        self.on_note_clicked = None
        self.on_note_constraint_changed = None
        self.on_note_constraints_reset = None

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
            suffix = self._tooltip_suffix()
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

    def _tooltip_suffix(self) -> str:
        return ""

    def _highlight_colour(self, pitch_class: int, fallback: str) -> QColor:
        return QColor(self.note_colours.get(pitch_class, fallback))

    def _paint_role_badge(self, painter: QPainter, pitch_class: int, badge_at) -> None:
        """Draw the role initials badge; ``badge_at(text)`` returns the badge rect."""
        roles = self.note_roles.get(pitch_class)
        if not roles:
            return
        text = "/".join(role[:1].upper() for role in sorted(roles))
        badge = badge_at(text)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor("#0f766e")))
        painter.drawRoundedRect(badge, 3, 3)
        painter.setPen(QColor("#f8fafc"))
        painter.drawText(badge, Qt.AlignCenter, text)

    def _constraint_colour(self, pitch_class: int) -> QColor | None:
        state = self.note_constraints.get(pitch_class)
        if state not in {"force", "exclude"}:
            return None
        return QColor("#16a34a" if state == "force" else "#dc2626")

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
        apply_note_override(self.note_constraints, pitch_class, state)
        if self.on_note_constraint_changed is not None:
            self.on_note_constraint_changed(pitch_class, state)
        self.update()


def _contrast_text_colour(colour: QColor) -> QColor:
    luminance = (colour.red() * 0.299) + (colour.green() * 0.587) + (colour.blue() * 0.114)
    return QColor("#111827" if luminance > 150 else "#f8fafc")
