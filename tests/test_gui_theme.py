from pitchstems.gui_theme import TRACK_COLORS, pitchstems_stylesheet


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
