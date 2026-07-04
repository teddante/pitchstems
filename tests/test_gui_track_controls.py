from types import SimpleNamespace

from pitchstems.gui_track_controls import (
    TRACK_CONTROL_MIN_HEIGHT,
    TrackControlEditorState,
    reset_track_control_widgets,
    track_control_panel_height,
    track_control_visibility,
    volume_value_text,
)


def test_track_control_panel_height_never_shrinks_below_usable_controls() -> None:
    assert track_control_panel_height(None) == TRACK_CONTROL_MIN_HEIGHT
    assert track_control_panel_height(42) == TRACK_CONTROL_MIN_HEIGHT
    assert track_control_panel_height(TRACK_CONTROL_MIN_HEIGHT + 20) == TRACK_CONTROL_MIN_HEIGHT + 20


def test_track_control_visibility_keeps_volume_rows_at_minimum_height() -> None:
    visible = track_control_visibility(TRACK_CONTROL_MIN_HEIGHT)

    assert visible.toggles
    assert visible.audio_volume
    assert visible.midi_volume


def test_track_control_visibility_hides_volume_rows_only_below_supported_height() -> None:
    visible = track_control_visibility(TRACK_CONTROL_MIN_HEIGHT - 1)

    assert visible.toggles
    assert not visible.audio_volume
    assert not visible.midi_volume


def test_track_control_editor_state_reads_saved_maps() -> None:
    track_visibility = {"bass": False}
    editor_state = {
        "track_analysis_enabled": {"bass": True},
        "track_audio_enabled": {"bass": False},
        "track_audio_volume": {"bass": 61},
        "track_midi_enabled": {"bass": True},
        "track_midi_volume": {"bass": 72},
    }

    state = TrackControlEditorState.from_editor_state(track_visibility, editor_state)

    assert state.track_visibility == {"bass": False}
    assert state.analysis_enabled == {"bass": True}
    assert state.audio_enabled == {"bass": False}
    assert state.audio_volume == {"bass": 61}
    assert state.midi_enabled == {"bass": True}
    assert state.midi_volume == {"bass": 72}


def test_track_control_editor_state_defaults_missing_maps() -> None:
    state = TrackControlEditorState.from_editor_state({"piano": True}, {})

    assert state.track_visibility == {"piano": True}
    assert state.analysis_enabled == {}
    assert state.audio_enabled == {}
    assert state.audio_volume == {}
    assert state.midi_enabled == {}
    assert state.midi_volume == {}


def test_reset_track_control_widgets_clears_widget_registries() -> None:
    window = SimpleNamespace(
        track_audio_checks={"bass": object()},
        track_audio_sliders={"bass": object()},
        track_midi_checks={"bass": object()},
        track_midi_sliders={"bass": object()},
        track_visibility_checks={"bass": object()},
        track_analysis_checks={"bass": object()},
        track_control_panels={"bass": object()},
        track_control_detail_rows={"bass": object()},
        track_control_top_spacer=object(),
        track_control_bottom_spacer=object(),
        track_master_checks={"audio": object()},
        show_all_tracks_button=object(),
        hidden_track_status=object(),
    )

    reset_track_control_widgets(window)

    assert window.track_audio_checks == {}
    assert window.track_audio_sliders == {}
    assert window.track_midi_checks == {}
    assert window.track_midi_sliders == {}
    assert window.track_visibility_checks == {}
    assert window.track_analysis_checks == {}
    assert window.track_control_panels == {}
    assert window.track_control_detail_rows == {}
    assert window.track_control_top_spacer is None
    assert window.track_control_bottom_spacer is None
    assert window.track_master_checks == {}
    assert window.show_all_tracks_button is None
    assert window.hidden_track_status is None


def test_volume_value_text_uses_percentage_units() -> None:
    assert volume_value_text(0) == "0%"
    assert volume_value_text(80) == "80%"
