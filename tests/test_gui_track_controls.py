from pitchstems.gui_track_controls import (
    TRACK_CONTROL_MIN_HEIGHT,
    track_control_panel_height,
    track_control_visibility,
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
