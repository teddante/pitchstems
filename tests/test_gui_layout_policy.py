from pitchstems.gui_editor_state import EditorLayoutPolicy


def test_editor_layout_policy_uses_compact_panels_below_desktop_width() -> None:
    policy = EditorLayoutPolicy(window_width=900)

    assert policy.compact is True
    assert policy.harmony_panel_min_width == 260
    assert policy.harmony_panel_width == 360
    assert policy.track_panel_min_width == 220
    assert policy.track_panel_width == 250


def test_editor_layout_policy_uses_roomier_panels_on_default_window() -> None:
    policy = EditorLayoutPolicy(window_width=1220)

    assert policy.compact is False
    assert policy.harmony_panel_min_width == 300
    assert policy.harmony_panel_width == 440
    assert policy.track_panel_min_width == 250
    assert policy.track_panel_width == 280
