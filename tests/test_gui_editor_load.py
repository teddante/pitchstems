from types import SimpleNamespace

from pitchstems.gui_editor_load import _apply_loaded_editor_result


def test_apply_loaded_editor_result_transfers_editor_state() -> None:
    editor_state = {"track_visibility": {"bass": True}}
    loaded = SimpleNamespace(
        base_project=object(),
        editor_project=object(),
        editor_state=editor_state,
        manual_chords=[object()],
        removed_chord_ranges=[(1.0, 2.0)],
    )
    window = SimpleNamespace(
        base_editor_project=None,
        editor_project=None,
        manual_chords=[],
        removed_chord_ranges=[],
    )

    assert _apply_loaded_editor_result(window, loaded) == editor_state
    assert window.base_editor_project is loaded.base_project
    assert window.editor_project is loaded.editor_project
    assert window.manual_chords == loaded.manual_chords
    assert window.removed_chord_ranges == loaded.removed_chord_ranges
