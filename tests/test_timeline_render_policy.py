from pitchstems.timeline_render_policy import TimelineRenderPolicy


def test_timeline_render_policy_uses_dense_mode_for_many_visible_notes() -> None:
    policy = TimelineRenderPolicy(pixels_per_second=92, visible_note_count=2500)

    assert policy.dense_render is True
    assert policy.enable_tooltips is False
    assert policy.draw_note_labels is False


def test_timeline_render_policy_shows_labels_only_when_zoomed_and_sparse() -> None:
    policy = TimelineRenderPolicy(pixels_per_second=160, visible_note_count=120)

    assert policy.dense_render is False
    assert policy.enable_tooltips is True
    assert policy.draw_note_labels is True
