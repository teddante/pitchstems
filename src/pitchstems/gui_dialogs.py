"""Inspector report dialogs and scale browser dialogs."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from pitchstems import harmony_panel
from pitchstems.harmony_report import (
    chord_gap_report,
    current_chord_analysis_report,
    theory_analysis_report,
)
from pitchstems.notation import spell_scale
from pitchstems.scale_chords import contained_chords_for_scale, searchable_scale_labels


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


def show_selected_scale_chords(window) -> None:
    candidate = harmony_panel.selected_theory_scale_candidate(window)
    if candidate is None:
        return
    dialog = QDialog(window)
    dialog.setWindowTitle(f"Scale Chords - {window.display_scale_candidate_label(candidate)}")
    layout = QVBoxLayout()
    summary = QLabel(
        f"{window.display_scale_candidate_label(candidate)}\n"
        f"{' - '.join(window.display_scale_candidate_notes(candidate))}"
    )
    summary.setWordWrap(True)
    layout.addWidget(summary)
    chord_list = QListWidget()
    chord_list.setAlternatingRowColors(True)
    populate_scale_chord_list(window, chord_list, candidate.root, candidate.scale)
    layout.addWidget(chord_list, 1)
    buttons = QDialogButtonBox(QDialogButtonBox.Close)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    dialog.setLayout(layout)
    dialog.resize(520, 460)
    dialog.exec()


def show_scale_browser(window) -> None:
    dialog = QDialog(window)
    dialog.setWindowTitle("Scale Browser")
    layout = QVBoxLayout()
    search = QLineEdit()
    search.setPlaceholderText("Search scales, families, aliases, or roots")
    layout.addWidget(search)
    body = QHBoxLayout()
    scale_list = QListWidget()
    scale_list.setAlternatingRowColors(True)
    chord_list = QListWidget()
    chord_list.setAlternatingRowColors(True)
    body.addWidget(scale_list, 1)
    body.addWidget(chord_list, 1)
    layout.addLayout(body, 1)
    buttons = QDialogButtonBox(QDialogButtonBox.Close)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    rows = searchable_scale_labels(window.selected_notation_preference())

    def refresh_scale_rows(_text: str = "") -> None:
        query = search.text().strip().lower()
        scale_list.clear()
        for label, root, scale in rows:
            haystack = f"{label} {scale.family} {' '.join(scale.aliases)}".lower()
            if query and query not in haystack:
                continue
            item = QListWidgetItem(
                f"{label}\n"
                f"{' - '.join(spell_scale(root, scale.intervals, window.selected_notation_preference()))}"
            )
            item.setData(Qt.UserRole, root)
            item.setData(Qt.UserRole + 1, scale)
            item.setToolTip(f"Family: {scale.family}\nAliases: {', '.join(scale.aliases) or '-'}")
            scale_list.addItem(item)
        if scale_list.count():
            scale_list.setCurrentRow(0)
        else:
            chord_list.clear()
            chord_list.addItem("No matching scales.")

    def refresh_chords_for_item(item) -> None:
        chord_list.clear()
        if item is None:
            return
        root = item.data(Qt.UserRole)
        scale = item.data(Qt.UserRole + 1)
        populate_scale_chord_list(window, chord_list, root, scale)

    scale_list.currentItemChanged.connect(lambda item, _previous: refresh_chords_for_item(item))
    search.textChanged.connect(refresh_scale_rows)
    dialog.setLayout(layout)
    dialog.resize(820, 520)
    refresh_scale_rows()
    dialog.exec()


def populate_scale_chord_list(window, chord_list, root: int, scale) -> None:
    chord_list.clear()
    chords = contained_chords_for_scale(root, scale, window.selected_notation_preference())
    if not chords:
        chord_list.addItem("No recognised contained chord shapes.")
        return
    for chord in chords:
        item = QListWidgetItem(
            f"{chord.category.title()}  degree {chord.degree}: {chord.label}\n"
            f"{' - '.join(chord.notes)}"
        )
        item.setToolTip(
            f"{chord.label}\n"
            f"Notes: {' - '.join(chord.notes)}\n"
            f"All listed tones are inside the selected scale."
        )
        chord_list.addItem(item)
