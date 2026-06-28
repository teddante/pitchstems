from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from pitchstems.editor_state import editor_bool, editor_int
from pitchstems.gui_helpers import clear_layout
from pitchstems.gui_theme import TRACK_COLORS


TRACK_CONTROL_MIN_HEIGHT = 96


@dataclass(frozen=True)
class TrackControlVisibility:
    toggles: bool
    audio_volume: bool
    midi_volume: bool


def track_control_panel_height(timeline_track_height: float | int | None) -> int:
    if timeline_track_height is None:
        return TRACK_CONTROL_MIN_HEIGHT
    return max(TRACK_CONTROL_MIN_HEIGHT, int(round(timeline_track_height)))


def track_control_visibility(height: float | int) -> TrackControlVisibility:
    """Keep the normal zoomed-out lane height large enough to show all controls."""
    compact_limit = TRACK_CONTROL_MIN_HEIGHT
    return TrackControlVisibility(
        toggles=height >= 38,
        audio_volume=height >= compact_limit,
        midi_volume=height >= compact_limit,
    )


def reset_track_control_widgets(window) -> None:
    window.track_audio_checks.clear()
    window.track_audio_sliders.clear()
    window.track_midi_checks.clear()
    window.track_midi_sliders.clear()
    window.track_visibility_checks.clear()
    window.track_analysis_checks.clear()
    window.track_control_panels.clear()
    window.track_control_detail_rows.clear()
    window.track_control_top_spacer = None
    window.track_control_bottom_spacer = None
    window.hidden_track_status = None


def rebuild_track_controls(window, editor_state: dict) -> None:
    clear_layout(window.playback_controls)
    reset_track_control_widgets(window)
    if window.editor_project is None:
        return

    track_visibility = window.editor_track_visibility
    analysis_enabled = editor_state.get("track_analysis_enabled", {})
    audio_enabled = editor_state.get("track_audio_enabled", {})
    audio_volume = editor_state.get("track_audio_volume", {})
    midi_enabled = editor_state.get("track_midi_enabled", {})
    midi_volume = editor_state.get("track_midi_volume", {})

    window.track_control_top_spacer = QWidget()
    window.track_control_top_spacer.setObjectName("trackControlHeader")
    window.track_control_top_spacer.setFixedHeight(int(window.timeline.chord_height))
    top_layout = QVBoxLayout()
    top_layout.setContentsMargins(8, 6, 8, 6)
    top_layout.setSpacing(4)
    window.track_control_top_spacer.setStyleSheet(
        """
        QWidget#trackControlHeader {
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
        }
        QLabel, QPushButton {
            border: 0;
        }
        """
    )
    top_title_row = QHBoxLayout()
    top_title_row.setContentsMargins(0, 0, 0, 0)
    top_title_row.setSpacing(6)
    top_title = QLabel("Tracks & Mix")
    top_title.setStyleSheet("font-weight: 700; color: #334155;")
    hidden_status = QLabel("")
    hidden_status.setStyleSheet("color: #64748b; font-size: 10px;")
    hidden_status.setToolTip("Tracks hidden with View off are removed from the timeline lanes. Use Show All to restore them.")
    show_all_button = QPushButton("Show All")
    show_all_button.setToolTip("Restore every track to the timeline.")
    show_all_button.clicked.connect(window.show_all_timeline_tracks)
    top_title_row.addWidget(top_title)
    top_title_row.addStretch(1)
    top_title_row.addWidget(hidden_status)
    top_layout.addLayout(top_title_row)
    top_layout.addWidget(show_all_button)
    window.track_control_top_spacer.setLayout(top_layout)
    window.hidden_track_status = hidden_status
    window.playback_controls.addWidget(window.track_control_top_spacer)

    for track in window.editor_project.tracks:
        add_track_control_row(
            window,
            track,
            editor_state={
                "track_visibility": track_visibility,
                "track_analysis_enabled": analysis_enabled,
                "track_audio_enabled": audio_enabled,
                "track_audio_volume": audio_volume,
                "track_midi_enabled": midi_enabled,
                "track_midi_volume": midi_volume,
            },
        )
    window.track_control_bottom_spacer = QWidget()
    window.track_control_bottom_spacer.setFixedHeight(34)
    window.playback_controls.addWidget(window.track_control_bottom_spacer)
    sync_track_control_panel(window)


def add_track_control_row(window, track, editor_state: dict) -> None:
    note_count = window.track_note_counts.get(track.name, 0)
    track_color = TRACK_COLORS.get(track.name.lower(), "#64748b")
    track_panel = QWidget()
    track_panel.setObjectName("trackControlRow")
    track_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    track_panel.setStyleSheet(
        f"""
        QWidget#trackControlRow {{
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-left: 3px solid {track_color};
            border-radius: 6px;
        }}
        QLabel, QCheckBox, QSlider {{
            border: 0;
            background: transparent;
        }}
        QCheckBox {{
            color: #334155;
            font-size: 9px;
            spacing: 2px;
        }}
        QSlider {{
            min-height: 12px;
            max-height: 12px;
        }}
        """
    )
    track_layout = QVBoxLayout()
    track_layout.setContentsMargins(10, 6, 8, 6)
    track_layout.setSpacing(3)

    title_row = QHBoxLayout()
    title_row.setContentsMargins(0, 0, 0, 0)
    title_row.setSpacing(6)
    title = QLabel(track.name)
    title.setStyleSheet("font-weight: 700; color: #0f172a;")
    notes = QLabel(f"{note_count:,} notes")
    notes.setStyleSheet("color: #64748b;")
    title_row.addWidget(title)
    title_row.addStretch(1)
    title_row.addWidget(notes)
    track_layout.addLayout(title_row)

    toggle_widget = QWidget()
    toggle_row = QHBoxLayout()
    toggle_row.setContentsMargins(0, 0, 0, 0)
    toggle_row.setSpacing(6)

    track_visibility = editor_state["track_visibility"]
    analysis_enabled = editor_state["track_analysis_enabled"]
    audio_enabled = editor_state["track_audio_enabled"]
    audio_volume = editor_state["track_audio_volume"]
    midi_enabled = editor_state["track_midi_enabled"]
    midi_volume = editor_state["track_midi_volume"]

    show_check = QCheckBox("View")
    show_check.setChecked(editor_bool(track_visibility.get(track.name), True))
    show_check.setToolTip(
        "Show this track's lane on the timeline. Turning it off hides this row too; use Show All to restore hidden tracks."
    )
    show_check.toggled.connect(lambda *_args: window.refresh_visible_tracks())
    window.track_visibility_checks[track.name] = show_check
    toggle_row.addWidget(show_check)

    analysis_check = QCheckBox("Chord")
    analysis_check.setChecked(
        editor_bool(
            analysis_enabled.get(track.name),
            editor_bool(track_visibility.get(track.name), True),
        )
    )
    analysis_check.setToolTip("Include this track's generated MIDI notes in the Harmony Inspector sample.")
    analysis_check.toggled.connect(lambda *_args: window.refresh_current_harmony(window.timeline.position, force=True))
    analysis_check.toggled.connect(lambda *_args: window.save_editor_state())
    analysis_check.toggled.connect(lambda *_args: window.refresh_timeline_track_summaries())
    window.track_analysis_checks[track.name] = analysis_check
    toggle_row.addWidget(analysis_check)

    audio_check = QCheckBox("Audio")
    audio_check.setChecked(editor_bool(audio_enabled.get(track.name), True))
    audio_check.setToolTip("Play this separated stem audio in the editor transport. Does not affect chord detection.")
    audio_slider = QSlider(Qt.Horizontal)
    audio_slider.setRange(0, 100)
    audio_slider.setValue(editor_int(audio_volume.get(track.name), 80, 0, 100))
    audio_slider.setToolTip("Separated stem audio volume.")
    audio_check.toggled.connect(lambda *_args: window.refresh_playback_mix())
    audio_check.toggled.connect(lambda *_args: window.save_editor_state())
    audio_check.toggled.connect(lambda *_args: window.refresh_timeline_track_summaries())
    audio_slider.valueChanged.connect(lambda *_args: window.refresh_playback_mix())
    audio_slider.valueChanged.connect(lambda *_args: window.save_editor_state())
    audio_slider.sliderReleased.connect(lambda *_args: window.refresh_timeline_track_summaries())
    window.track_audio_checks[track.name] = audio_check
    window.track_audio_sliders[track.name] = audio_slider
    toggle_row.addWidget(audio_check)

    has_midi_notes = note_count > 0
    midi_check = QCheckBox("MIDI")
    midi_check.setChecked(has_midi_notes and editor_bool(midi_enabled.get(track.name), False))
    midi_check.setEnabled(has_midi_notes)
    midi_check.setToolTip("Play this stem's generated MIDI preview audio. Missing previews render only when this MIDI track is turned on.")
    midi_slider = QSlider(Qt.Horizontal)
    midi_slider.setRange(0, 100)
    midi_slider.setValue(editor_int(midi_volume.get(track.name), 70, 0, 100))
    midi_slider.setEnabled(has_midi_notes)
    midi_slider.setToolTip("MIDI preview volume.")
    midi_check.toggled.connect(
        lambda checked, stem_name=track.name: window.handle_midi_track_toggled(stem_name, checked)
    )
    midi_slider.valueChanged.connect(lambda *_args: window.refresh_playback_mix())
    midi_slider.valueChanged.connect(lambda *_args: window.save_editor_state())
    midi_slider.sliderReleased.connect(lambda *_args: window.refresh_timeline_track_summaries())
    window.track_midi_checks[track.name] = midi_check
    window.track_midi_sliders[track.name] = midi_slider
    toggle_row.addWidget(midi_check)
    toggle_row.addStretch(1)
    toggle_widget.setLayout(toggle_row)
    track_layout.addWidget(toggle_widget)

    audio_widget = QWidget()
    slider_row = QHBoxLayout()
    slider_row.setContentsMargins(0, 0, 0, 0)
    slider_row.setSpacing(6)
    audio_label = QLabel("Audio")
    audio_label.setMinimumWidth(42)
    audio_label.setStyleSheet("color: #64748b;")
    audio_label.setToolTip("Separated stem audio volume.")
    slider_row.addWidget(audio_label)
    slider_row.addWidget(audio_slider)
    audio_widget.setLayout(slider_row)
    track_layout.addWidget(audio_widget)

    midi_widget = QWidget()
    midi_slider_row = QHBoxLayout()
    midi_slider_row.setContentsMargins(0, 0, 0, 0)
    midi_slider_row.setSpacing(6)
    midi_label = QLabel("MIDI")
    midi_label.setMinimumWidth(42)
    midi_label.setStyleSheet("color: #64748b;")
    midi_label.setToolTip("Generated MIDI preview volume.")
    midi_slider_row.addWidget(midi_label)
    midi_slider_row.addWidget(midi_slider)
    midi_widget.setLayout(midi_slider_row)
    track_layout.addWidget(midi_widget)
    track_panel.setLayout(track_layout)
    window.track_control_panels[track.name] = track_panel
    window.track_control_detail_rows[track.name] = (toggle_widget, audio_widget, midi_widget)
    window.playback_controls.addWidget(track_panel)


def sync_track_control_panel(window) -> None:
    if window.track_control_top_spacer is not None:
        window.track_control_top_spacer.setFixedHeight(int(window.timeline.chord_height))
    if window.track_control_bottom_spacer is not None:
        window.track_control_bottom_spacer.setFixedHeight(34)
    if window.editor_project is None:
        return
    hidden_tracks = [
        track.name
        for track in window.editor_project.tracks
        if window.track_visibility_checks.get(track.name)
        and not window.track_visibility_checks[track.name].isChecked()
    ]
    if window.hidden_track_status is not None:
        if hidden_tracks:
            window.hidden_track_status.setText(f"Hidden: {len(hidden_tracks)}")
            window.hidden_track_status.setToolTip("Hidden timeline tracks: " + ", ".join(hidden_tracks))
        else:
            window.hidden_track_status.setText("All tracks visible")
            window.hidden_track_status.setToolTip("No timeline tracks are hidden.")
    for track in window.editor_project.tracks:
        panel = window.track_control_panels.get(track.name)
        if panel is None:
            continue
        visible_check = window.track_visibility_checks.get(track.name)
        is_visible = visible_check is None or visible_check.isChecked()
        panel.setVisible(is_visible)
        if not is_visible:
            continue
        geometry = window.timeline.track_geometries.get(track.name.lower())
        height = track_control_panel_height(geometry[1] if geometry else None)
        panel.setFixedHeight(height)
        detail_rows = window.track_control_detail_rows.get(track.name)
        if detail_rows is None:
            continue
        toggle_widget, audio_widget, midi_widget = detail_rows
        visibility = track_control_visibility(height)
        toggle_widget.setVisible(visibility.toggles)
        audio_widget.setVisible(visibility.audio_volume)
        midi_widget.setVisible(visibility.midi_volume)
    window.playback_controls_widget.adjustSize()
