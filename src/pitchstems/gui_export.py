from __future__ import annotations

import threading
from pathlib import Path

from pitchstems.export_files import (
    ExportCancelledError,
    ExportItem,
    ExportSummary,
    build_export_items,
    copy_export_items,
    export_collisions,
)
from pitchstems.gui_jobs import thread_is_alive


def export_selected_files(window) -> None:
    if thread_is_alive(getattr(window, "export_worker", None)):
        window.statusBar().showMessage("An export is already running.", 4000)
        return
    if window.current_result is None:
        window.append_log("Open or run a project before exporting files.")
        window.statusBar().showMessage("Open or run a project before exporting files.", 4000)
        return

    items = build_export_items(window.current_result)
    if not items:
        window.append_log("No stems, MIDI, or notes CSV files are available to export.")
        window.statusBar().showMessage("No files are available to export.", 4000)
        return

    dialog = ExportSelectedFilesDialog(
        window,
        items,
        window.current_result.project_dir / "export",
    )
    if not dialog.exec():
        return

    selected_items = dialog.selected_items()
    destination = dialog.destination()
    if not selected_items:
        window.append_log("Choose at least one file to export.")
        window.statusBar().showMessage("Choose at least one file to export.", 4000)
        return

    collisions = export_collisions(selected_items, destination)
    overwrite = False
    if collisions:
        from PySide6.QtWidgets import QMessageBox

        shown = "\n".join(str(path) for path in collisions[:8])
        if len(collisions) > 8:
            shown += f"\n...and {len(collisions) - 8} more"
        answer = QMessageBox.question(
            window,
            "Replace existing export files?",
            f"{len(collisions)} selected destination file(s) already exist:\n\n{shown}\n\nReplace them?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        overwrite = True

    cancel_event = threading.Event()
    window.export_cancel_event = cancel_event
    window.set_processing_state(True)
    window.begin_activity("Exporting selected files...")
    window.append_log(f"Exporting {len(selected_items)} files to {destination.expanduser()}...")

    def progress(copied: int, total: int, target: Path) -> None:
        window.messages.put(("EXPORT_PROGRESS", copied, total, target.name))

    def run_export() -> None:
        try:
            summary = copy_export_items(
                selected_items,
                destination,
                overwrite=overwrite,
                cancelled=cancel_event.is_set,
                progress=progress,
            )
            window.messages.put(("EXPORT_COMPLETE", summary, None))
        except Exception as exc:
            window.messages.put(("EXPORT_COMPLETE", None, exc))

    window.export_worker = threading.Thread(target=run_export, daemon=True)
    window.export_worker.start()


def finish_export(window, summary: ExportSummary | None, error: Exception | None) -> None:
    window.export_worker = None
    window.export_cancel_event = None
    window.set_processing_state(False)
    if error is not None:
        if isinstance(error, ExportCancelledError):
            window.append_log("Export cancelled.")
            window.end_activity("Export cancelled")
            window.statusBar().showMessage("Export cancelled.", 4000)
            _close_after_export_if_requested(window)
            return
        window.logger.error("Could not export selected files: %s", error)
        window.append_log(f"Could not export selected files: {error}")
        window.end_activity("Export failed")
        window.statusBar().showMessage("Could not export selected files.", 5000)
        _close_after_export_if_requested(window)
        return
    if summary is None:
        window.end_activity("Export failed")
        _close_after_export_if_requested(window)
        return
    message = f"Exported {summary.file_count} files to {summary.destination}"
    window.latest_output_dir = summary.destination
    window.append_log(message)
    window.end_activity("Export complete")
    window.statusBar().showMessage(message, 5000)
    _close_after_export_if_requested(window)


def _close_after_export_if_requested(window) -> None:
    if not getattr(window, "close_after_export", False):
        return
    window.close_after_export = False
    from pitchstems.gui_shutdown import begin_auxiliary_shutdown

    begin_auxiliary_shutdown(window)
    window.close()


class ExportSelectedFilesDialog:
    def __init__(self, parent, items: list[ExportItem], default_destination: Path) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QCheckBox,
            QDialog,
            QDialogButtonBox,
            QFileDialog,
            QGroupBox,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QPushButton,
            QScrollArea,
            QVBoxLayout,
            QWidget,
        )

        self._checks: list[tuple[ExportItem, QCheckBox]] = []
        self._category_checks: dict[str, list[QCheckBox]] = {}
        self._dialog = QDialog(parent)
        self._dialog.setWindowTitle("Export Selected Files")
        self._dialog.resize(520, 420)

        layout = QVBoxLayout()
        intro = QLabel("Choose the project files to copy.")
        intro.setStyleSheet("color: #4b5563;")
        layout.addWidget(intro)

        destination_row = QHBoxLayout()
        destination_row.setSpacing(8)
        destination_row.addWidget(QLabel("Destination"))
        self._destination = QLineEdit(str(default_destination))
        destination_row.addWidget(self._destination, 1)
        browse = QPushButton("Browse...")
        browse.clicked.connect(lambda: self._browse_destination(QFileDialog))
        destination_row.addWidget(browse)
        layout.addLayout(destination_row)

        selection_row = QHBoxLayout()
        selection_row.setSpacing(8)
        defaults = QPushButton("Defaults")
        defaults.clicked.connect(self.select_default_items)
        selection_row.addWidget(defaults)
        all_items = QPushButton("All")
        all_items.clicked.connect(self.select_all_items)
        selection_row.addWidget(all_items)
        none = QPushButton("None")
        none.clicked.connect(self.clear_selected_items)
        selection_row.addWidget(none)
        self._selection_summary = QLabel("")
        self._selection_summary.setStyleSheet("color: #4b5563;")
        selection_row.addWidget(self._selection_summary, 1)
        layout.addLayout(selection_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_body = QWidget()
        scroll_layout = QVBoxLayout()
        scroll_layout.setSpacing(8)
        for category in ("Project", "Source Audio", "Stems", "MIDI", "Combined MIDI", "Notes CSV"):
            category_items = [item for item in items if item.category == category]
            if not category_items:
                continue
            group = QGroupBox(category)
            group_layout = QVBoxLayout()
            group_layout.setSpacing(4)
            category_row = QHBoxLayout()
            category_row.setSpacing(6)
            category_row.addStretch(1)
            category_all = QPushButton("All")
            category_all.clicked.connect(lambda _checked=False, name=category: self.select_category_items(name))
            category_row.addWidget(category_all)
            category_none = QPushButton("None")
            category_none.clicked.connect(lambda _checked=False, name=category: self.clear_category_items(name))
            category_row.addWidget(category_none)
            group_layout.addLayout(category_row)
            for item in category_items:
                check = QCheckBox(f"{item.label} -> {item.relative_path.as_posix()}")
                check.setChecked(item.default_selected)
                check.setToolTip(str(item.source_path))
                check.stateChanged.connect(lambda _state: self._refresh_selection_summary())
                self._checks.append((item, check))
                self._category_checks.setdefault(category, []).append(check)
                group_layout.addWidget(check)
            group.setLayout(group_layout)
            scroll_layout.addWidget(group)
        scroll_layout.addStretch(1)
        scroll_body.setLayout(scroll_layout)
        scroll.setWidget(scroll_body)
        layout.addWidget(scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Export")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self._dialog.reject)
        layout.addWidget(buttons)
        self._dialog.setLayout(layout)
        self._refresh_selection_summary()

    def exec(self) -> int:
        return self._dialog.exec()

    def selected_items(self) -> list[ExportItem]:
        return [item for item, check in self._checks if check.isChecked()]

    def select_default_items(self) -> None:
        for item, check in self._checks:
            check.setChecked(item.default_selected)
        self._refresh_selection_summary()

    def select_all_items(self) -> None:
        for _item, check in self._checks:
            check.setChecked(True)
        self._refresh_selection_summary()

    def clear_selected_items(self) -> None:
        for _item, check in self._checks:
            check.setChecked(False)
        self._refresh_selection_summary()

    def select_category_items(self, category: str) -> None:
        for check in self._category_checks.get(category, []):
            check.setChecked(True)
        self._refresh_selection_summary()

    def clear_category_items(self, category: str) -> None:
        for check in self._category_checks.get(category, []):
            check.setChecked(False)
        self._refresh_selection_summary()

    def destination(self) -> Path:
        return Path(self._destination.text()).expanduser()

    def _refresh_selection_summary(self) -> None:
        selected = len(self.selected_items())
        total = len(self._checks)
        self._selection_summary.setText(f"{selected} of {total} files selected")

    def _browse_destination(self, file_dialog) -> None:
        directory = file_dialog.getExistingDirectory(
            self._dialog,
            "Choose export destination",
            self._destination.text(),
        )
        if directory:
            self._destination.setText(directory)

    def _accept(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        if not self.selected_items():
            QMessageBox.warning(self._dialog, "Export Selected Files", "Choose at least one file to export.")
            return
        if not self._destination.text().strip():
            QMessageBox.warning(self._dialog, "Export Selected Files", "Choose an export destination.")
            return
        self._dialog.accept()
