from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFont, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pitchstems.gui_theme import (
    DEFAULT_UI_SCALE,
    UI_SCALE_STEP,
    normalized_ui_scale,
    pitchstems_stylesheet,
)
from pitchstems.gui_track_controls import sync_track_control_panel
from pitchstems import (
    gui_editor_actions,
    gui_export,
    gui_project_flow,
)

class WindowShellMixin:
    def begin_activity(self, message: str, busy: bool = True) -> None:
        self.activity_depth += 1
        self.activity_label.setText(message)
        self.statusBar().showMessage(message)
        if busy:
            self.activity_bar.setRange(0, 0)
        else:
            self.activity_bar.setRange(0, 1)
            self.activity_bar.setValue(0)
        QApplication.processEvents()

    def end_activity(self, message: str = "Ready") -> None:
        self.activity_depth = max(0, self.activity_depth - 1)
        if self.activity_depth:
            return
        self.activity_label.setText(message)
        self.activity_bar.setRange(0, 1)
        self.activity_bar.setValue(1)
        self.statusBar().showMessage(message, 4000)
        QApplication.processEvents()

    def reset_activity(self, message: str = "Ready") -> None:
        self.activity_depth = 0
        self.activity_label.setText(message)
        self.activity_bar.setRange(0, 1)
        self.activity_bar.setValue(1)
        self.statusBar().showMessage(message, 4000)

    def begin_timeline_redraw(self) -> None:
        if self.activity_depth:
            return
        self.activity_label.setText("Redrawing timeline...")
        self.activity_bar.setRange(0, 0)

    def finish_timeline_redraw(self) -> None:
        sync_track_control_panel(self)
        self.sync_track_control_scroll(self.timeline.verticalScrollBar().value())
        if self.activity_depth:
            return
        self.activity_label.setText("Ready")
        self.activity_bar.setRange(0, 1)
        self.activity_bar.setValue(1)
        message = self.timeline.last_redraw_stats or "Timeline ready"
        self.statusBar().showMessage(message, 2500)

    def set_activity_message(self, message: str) -> None:
        self.activity_label.setText(message)
        self.statusBar().showMessage(message)
        QApplication.processEvents()

    def build_workspace_shell(self) -> QWidget:
        root = QWidget()
        root.setObjectName("appShell")
        root_layout = QHBoxLayout()
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        rail = QFrame()
        rail.setObjectName("sideRail")
        rail.setFixedWidth(90)
        rail_layout = QVBoxLayout()
        rail_layout.setContentsMargins(8, 10, 6, 10)
        rail_layout.setSpacing(6)

        brand = QLabel("PitchStems")
        brand.setObjectName("brandTitle")
        brand.setAlignment(Qt.AlignCenter)
        rail_layout.addWidget(brand)
        rail_layout.addSpacing(14)

        self.workspace_nav_group = QButtonGroup(self)
        self.workspace_nav_group.setExclusive(True)
        for label, tab_index in (
            ("Pipeline", 0),
            ("Editor", 1),
        ):
            button = QPushButton(label)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, index=tab_index: self.main_tabs.setCurrentIndex(index))
            self.workspace_nav_group.addButton(button)
            rail_layout.addWidget(button)
            self.workspace_nav_buttons[label] = button
        rail_layout.addStretch(1)

        help_button = QPushButton("Help")
        help_button.setObjectName("navButton")
        help_button.clicked.connect(self.show_timeline_controls)
        rail_layout.addWidget(help_button)
        rail.setLayout(rail_layout)

        workspace = QWidget()
        workspace_layout = QVBoxLayout()
        workspace_layout.setContentsMargins(12, 10, 12, 0)
        workspace_layout.setSpacing(10)
        workspace_layout.addWidget(self.build_top_bar())
        workspace_layout.addWidget(self.build_project_strip())
        workspace_layout.addWidget(self.main_tabs, 1)
        workspace.setLayout(workspace_layout)

        root_layout.addWidget(rail)
        root_layout.addWidget(workspace, 1)
        root.setLayout(root_layout)
        self.sync_workspace_nav(self.main_tabs.currentIndex())
        return root

    def build_top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("topBar")
        layout = QHBoxLayout()
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)
        layout.addWidget(self.play_button)
        layout.addWidget(self.play_review_button)
        layout.addWidget(self.previous_chord_button)
        layout.addWidget(self.next_chord_button)
        layout.addWidget(self.stop_button)
        layout.addWidget(self.fit_song_button)
        layout.addWidget(self.fit_review_button)
        position_label = QLabel("Position")
        position_label.setObjectName("eyebrow")
        layout.addWidget(position_label)
        layout.addWidget(self.editor_position)
        layout.addWidget(self.current_chord, 1)
        layout.addStretch(1)
        layout.addWidget(self.export_button)
        layout.addWidget(self.cancel_button)
        layout.addWidget(self.run_midi)
        layout.addWidget(self.run_full)
        bar.setLayout(layout)
        return bar

    def build_project_strip(self) -> QWidget:
        strip = QFrame()
        strip.setObjectName("projectStrip")
        layout = QHBoxLayout()
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)
        project_label = QLabel("Project")
        project_label.setObjectName("eyebrow")
        layout.addWidget(project_label)
        layout.addWidget(self.editor_summary, 1)
        status_label = QLabel("Status")
        status_label.setObjectName("eyebrow")
        layout.addWidget(status_label)
        layout.addWidget(self.separation_status)
        strip.setLayout(layout)
        return strip

    def sync_workspace_nav(self, index: int) -> None:
        target = "Pipeline" if index == 0 else "Editor"
        button = self.workspace_nav_buttons.get(target)
        if button is not None:
            button.setChecked(True)

    def create_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        self._add_action(file_menu, "&Open Audio...", "Ctrl+O", lambda: gui_project_flow.pick_audio(self))
        self._add_action(file_menu, "Open &Project...", "Ctrl+Shift+O", lambda: gui_project_flow.pick_project(self))
        self.recent_projects_menu = file_menu.addMenu("Open &Recent")
        gui_project_flow.refresh_recent_projects_menu(self)
        file_menu.addSeparator()
        self._add_action(file_menu, "&Save Project", "Ctrl+S", lambda: gui_project_flow.save_project_now(self))
        self.export_action = self._add_action(
            file_menu,
            "Export Selected Files...",
            None,
            lambda: gui_export.export_selected_files(self),
        )
        self.export_action.setEnabled(False)
        self._add_action(file_menu, "Choose Output &Folder...", None, lambda: gui_project_flow.pick_output_dir(self))
        self._add_action(file_menu, "Open Output Folder", "Ctrl+E", self.open_latest_output)
        self._add_action(file_menu, "Open Logs Folder", None, lambda: gui_project_flow.open_logs_folder(self))
        file_menu.addSeparator()
        self._add_action(file_menu, "E&xit", "Alt+F4", self.close)

        run_menu = self.menuBar().addMenu("&Run")
        self._add_action(run_menu, "Run Separation + MIDI", "F5", self.start_full_processing)
        self._add_action(run_menu, "Rerun MIDI Only", "Shift+F5", self.start_midi_processing)
        self._add_action(run_menu, "Cancel Processing", None, self.cancel_processing)

        view_menu = self.menuBar().addMenu("&View")
        self._add_action(view_menu, "Pipeline", "Ctrl+1", lambda: self.main_tabs.setCurrentIndex(0))
        self._add_action(view_menu, "Editor", "Ctrl+2", lambda: self.main_tabs.setCurrentIndex(1))
        view_menu.addSeparator()
        zoom_time_in = self._add_action(
            view_menu,
            "Zoom Time In",
            None,
            lambda: self.timeline.zoom_horizontal(1.18),
        )
        zoom_time_in.setShortcuts([QKeySequence("Ctrl++"), QKeySequence("Ctrl+=")])
        self._add_action(view_menu, "Zoom Time Out", "Ctrl+-", lambda: self.timeline.zoom_horizontal(1 / 1.18))
        # Pitch zoom uses Alt so it cannot collide with UI zoom on Ctrl+Shift+=/-
        # (Ctrl+Shift+= is also reported as Ctrl+Shift++ on US layouts).
        zoom_pitch_in = self._add_action(
            view_menu,
            "Zoom Pitch In",
            None,
            lambda: self.timeline.zoom_vertical(1.18),
        )
        zoom_pitch_in.setShortcuts([QKeySequence("Alt+="), QKeySequence("Alt++")])
        self._add_action(
            view_menu,
            "Zoom Pitch Out",
            "Alt+-",
            lambda: self.timeline.zoom_vertical(1 / 1.18),
        )
        self._add_action(view_menu, "Reset Timeline Zoom", "Ctrl+0", self.timeline.reset_zoom)
        view_menu.addSeparator()
        self._add_action(view_menu, "UI Zoom In", "Ctrl+Shift+=", lambda: self.change_ui_scale(UI_SCALE_STEP))
        self._add_action(view_menu, "UI Zoom Out", "Ctrl+Shift+-", lambda: self.change_ui_scale(-UI_SCALE_STEP))
        self._add_action(view_menu, "Reset UI Zoom", "Ctrl+Shift+0", self.reset_ui_scale)
        self._add_action(
            view_menu,
            "Fit Whole Song",
            "Ctrl+Alt+0",
            lambda: gui_editor_actions.fit_editor_song_to_view(self),
        )
        self._add_action(
            view_menu,
            "Fit Review Target",
            "Ctrl+Alt+F",
            lambda: gui_editor_actions.fit_editor_review_to_view(self),
        )
        view_menu.addSeparator()
        self._add_action(view_menu, "Previous Chord", "Alt+Left", lambda: self.select_review_chord(-1))
        self._add_action(view_menu, "Next Chord", "Alt+Right", lambda: self.select_review_chord(1))

        help_menu = self.menuBar().addMenu("&Help")
        self._add_action(help_menu, "Show Timeline Controls", None, self.show_timeline_controls)

    def _add_action(self, menu, text: str, shortcut: str | None, callback) -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(callback)
        menu.addAction(action)
        return action

    def change_ui_scale(self, delta: float) -> None:
        self.apply_ui_scale(self.ui_scale + delta)

    def reset_ui_scale(self) -> None:
        self.apply_ui_scale(DEFAULT_UI_SCALE)

    def apply_ui_scale(self, scale: float, persist: bool = True) -> None:
        self.ui_scale = normalized_ui_scale(scale)
        app = QApplication.instance()
        if app is not None:
            font = self.base_app_font
            scaled_font = QFont(font)
            if font.pointSizeF() > 0:
                scaled_font.setPointSizeF(font.pointSizeF() * self.ui_scale)
            elif font.pixelSize() > 0:
                scaled_font.setPixelSize(max(1, round(font.pixelSize() * self.ui_scale)))
            app.setFont(scaled_font)
            app.setStyleSheet(pitchstems_stylesheet(self.ui_scale))
        if persist:
            self.settings.setValue("ui_scale", self.ui_scale)
            self.updateGeometry()
            self.adjustSize()
            sync_track_control_panel(self)
            self.statusBar().showMessage(f"UI zoom: {self.ui_scale:.0%}", 2500)

    def show_timeline_controls(self) -> None:
        self.statusBar().showMessage(
            "Timeline controls: Space plays/pauses; Play Review loops one selected range or chord; Prev/Next Chord or Alt+Left/Right steps through chords for review; Fit Song or Ctrl+Alt+0 shows the full song; Ctrl+Alt+F fits the selected review target; drag the chord lane or Shift+drag the timeline to select a chord-analysis range; Ctrl+drag adds another selected range; Esc clears selection; click/drag sets playhead; wheel scrolls vertically; Shift+wheel scrolls horizontally; Ctrl+wheel zooms time; Ctrl+Shift+wheel zooms pitch; middle/right drag pans.",
            12000,
        )
