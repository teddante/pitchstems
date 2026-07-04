from pitchstems.gui_theme import (
    MAX_UI_SCALE,
    MIN_UI_SCALE,
    TRACK_COLORS,
    normalized_ui_scale,
    pitchstems_stylesheet,
)


def test_pitchstems_stylesheet_defines_core_workspace_surfaces() -> None:
    stylesheet = pitchstems_stylesheet()

    assert "QWidget#appShell" in stylesheet
    assert "QFrame#sideRail" in stylesheet
    assert "QPushButton#primaryAction" in stylesheet
    assert "#0b74de" in stylesheet


def test_track_palette_matches_editor_lane_roles() -> None:
    assert TRACK_COLORS["bass"] == "#22c55e"
    assert TRACK_COLORS["guitar"] == "#f59e0b"
    assert TRACK_COLORS["piano"] == "#8b5cf6"
    assert TRACK_COLORS["vocals"] == "#0b74de"


def test_ui_scale_is_clamped_to_supported_range() -> None:
    assert normalized_ui_scale(0.1) == MIN_UI_SCALE
    assert normalized_ui_scale(9.0) == MAX_UI_SCALE
    assert normalized_ui_scale("not a number") == 1.0


def test_pitchstems_stylesheet_scales_core_font_size() -> None:
    assert "font-size: 12px;" in pitchstems_stylesheet(1.0)
    assert "font-size: 14px;" in pitchstems_stylesheet(1.2)
