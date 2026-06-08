from pitchstems.gui_editor_model import EditorSummaryModel


def test_editor_summary_model_empty_project() -> None:
    model = EditorSummaryModel(track_count=0, note_count=0, duration_seconds=0.0)

    assert model.has_timeline is False
    assert model.fit_song_enabled is False
    assert model.summary == "Run separation + MIDI to build an editor timeline."


def test_editor_summary_model_loaded_project() -> None:
    model = EditorSummaryModel(track_count=2, note_count=150, duration_seconds=92.4)

    assert model.has_timeline is True
    assert model.fit_song_enabled is True
    assert "2 tracks" in model.summary
    assert "150 notes" in model.summary
