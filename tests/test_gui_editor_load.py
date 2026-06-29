from types import SimpleNamespace

from pitchstems.gui_editor_load import _apply_current_result_state, _apply_loaded_editor_result


class _PreviewJobs:
    def __init__(self) -> None:
        self.next_count = 0

    def next(self) -> None:
        self.next_count += 1


def test_apply_current_result_state_transfers_pipeline_result_state(tmp_path) -> None:
    result = SimpleNamespace(
        project_dir=tmp_path / "song.pitchstems",
        normalized_audio=tmp_path / "song.pitchstems" / "work" / "song.wav",
        stems=[object()],
    )
    midi_preview_jobs = _PreviewJobs()
    window = SimpleNamespace(
        current_result=None,
        midi_preview_jobs=midi_preview_jobs,
        current_stems=[],
        current_input_stem=None,
        latest_output_dir=None,
        base_editor_project=object(),
        editor_project=object(),
        manual_chords=[object()],
        removed_chord_ranges=[(1.0, 2.0)],
        rendering_midi_previews={"bass"},
    )

    _apply_current_result_state(window, result)

    assert window.current_result is result
    assert midi_preview_jobs.next_count == 1
    assert window.current_stems == result.stems
    assert window.current_input_stem == "song"
    assert window.latest_output_dir == result.project_dir
    assert window.base_editor_project is None
    assert window.editor_project is None
    assert window.manual_chords == []
    assert window.removed_chord_ranges == []
    assert window.rendering_midi_previews == set()


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
