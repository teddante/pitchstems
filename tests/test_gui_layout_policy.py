from pitchstems.gui_layout_policy import EditorLayoutPolicy, PipelineLayoutPolicy


def test_editor_layout_policy_uses_compact_panels_below_desktop_width() -> None:
    policy = EditorLayoutPolicy(window_width=900)

    assert policy.compact is True
    assert policy.harmony_panel_min_width == 260
    assert policy.harmony_panel_width == 380
    assert policy.track_panel_min_width == 240
    assert policy.track_panel_width == 240


def test_editor_layout_policy_uses_roomier_panels_on_default_window() -> None:
    policy = EditorLayoutPolicy(window_width=1220)

    assert policy.compact is False
    assert policy.harmony_panel_min_width == 300
    assert policy.harmony_panel_width == 460
    assert policy.track_panel_min_width == 280
    assert policy.track_panel_width == 280


def test_pipeline_layout_policy_keeps_intro_copy_short() -> None:
    policy = PipelineLayoutPolicy()

    assert len(policy.pipeline_intro) <= 110
    assert "BS-RoFormer" in policy.pipeline_intro
