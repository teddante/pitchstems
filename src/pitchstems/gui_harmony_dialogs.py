from __future__ import annotations

from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QTextEdit, QVBoxLayout

from pitchstems.chord_gap_analysis import chord_gap_report
from pitchstems.harmony_report import current_chord_analysis_report
from pitchstems.theory import theory_analysis_report


def show_report_dialog(parent, title: str, report: str) -> None:
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    layout = QVBoxLayout()
    text = QTextEdit()
    text.setReadOnly(True)
    text.setPlainText(report)
    layout.addWidget(text)
    close_button = QPushButton("Close")
    close_button.clicked.connect(dialog.accept)
    button_row = QHBoxLayout()
    button_row.addStretch(1)
    button_row.addWidget(close_button)
    layout.addLayout(button_row)
    dialog.setLayout(layout)
    dialog.resize(820, 680)
    dialog.exec()


def inspect_current_chord_analysis(window) -> None:
    if window.editor_project is None:
        return
    show_report_dialog(
        window,
        "Harmony Inspector Calculation",
        current_chord_analysis_report(window),
    )


def inspect_current_theory_analysis(window) -> None:
    if window.current_theory_analysis is None:
        return
    show_report_dialog(
        window,
        "Theory Inspector Calculation",
        theory_analysis_report(window.current_theory_analysis),
    )


def inspect_current_gap_suggestions(window) -> None:
    if window.current_chord_gap_analysis is None:
        return
    show_report_dialog(
        window,
        "Chord Gap Suggestions",
        chord_gap_report(window.current_chord_gap_analysis),
    )
