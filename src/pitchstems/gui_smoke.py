from __future__ import annotations


def run_startup_smoke(window) -> None:
    _assert(window.windowTitle() == "PitchStems", "window title")
    _assert(window.main_tabs.count() >= 2, "main tabs")
    tab_names = [window.main_tabs.tabText(index) for index in range(window.main_tabs.count())]
    _assert("Pipeline" in tab_names, "pipeline tab")
    _assert("Editor" in tab_names, "editor tab")

    window.main_tabs.setCurrentIndex(tab_names.index("Editor"))
    _assert(window.timeline.project is None, "empty startup timeline")
    _assert(window.play_button.isEnabled(), "play available before project load")
    _assert(window.play_button.text() == "Play", "play button text")
    _assert(not window.stop_button.isEnabled(), "stop disabled before playback")
    _assert(not window.fit_song_button.isEnabled(), "fit disabled before project load")
    _assert(window.editor_position.text() == "00:00.000", "initial editor position")

    window.main_tabs.setCurrentIndex(tab_names.index("Pipeline"))
    _assert(window.run_full.isEnabled(), "run button enabled")
    _assert(not window.run_midi.isEnabled(), "rerun midi disabled before project load")
    _assert(window.generate_midi.isChecked(), "generate MIDI default")
    _assert("drums" in window.midi_stem_checks, "MIDI stem checks populated")
    _assert(not window.midi_stem_checks["drums"].isChecked(), "drums MIDI default off")

    menu_titles = {action.text() for action in window.menuBar().actions()}
    _assert("&File" in menu_titles, "file menu")
    _assert("&Run" in menu_titles, "run menu")
    _assert("&View" in menu_titles, "view menu")
    _assert("&Help" in menu_titles, "help menu")
    _assert(window.recent_projects_menu is not None, "recent projects menu created")

    window.show_timeline_controls()
    _assert("Timeline controls:" in window.statusBar().currentMessage(), "timeline controls status")

def _assert(condition: bool, label: str) -> None:
    if not condition:
        raise RuntimeError(f"GUI startup smoke failed: {label}")
