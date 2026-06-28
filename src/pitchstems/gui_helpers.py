from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from PySide6.QtWidgets import QLabel


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


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
