from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QListWidget


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


def text_label(text: str = "", role: str = "helpText", *, wrap: bool = True) -> QLabel:
    """Secondary label styled by a gui_theme object-name role (helpText, mutedText, ...)."""
    label = QLabel(text)
    label.setObjectName(role)
    label.setWordWrap(wrap)
    return label


def wrapping_list(min_height: int) -> QListWidget:
    """List with wrapped multi-line rows, no horizontal scrolling, and alternating row colours."""
    widget = QListWidget()
    widget.setMinimumHeight(min_height)
    widget.setWordWrap(True)
    widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    widget.setAlternatingRowColors(True)
    return widget


def section_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("sectionTitle")
    return label


@contextmanager
def blocked_signals(widget) -> Iterator[None]:
    previous = widget.blockSignals(True)
    try:
        yield
    finally:
        widget.blockSignals(previous)
