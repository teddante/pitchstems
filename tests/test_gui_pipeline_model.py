from pitchstems.gui_pipeline_model import PipelinePageModel


def test_pipeline_page_model_disables_run_controls_while_busy() -> None:
    model = PipelinePageModel(busy=True, has_result=True, generate_midi=True)

    assert model.drop_zone_enabled is False
    assert model.run_full_enabled is False
    assert model.run_midi_enabled is False
    assert model.export_enabled is False
    assert model.cancel_enabled is True
    assert model.midi_stem_checks_enabled is False


def test_pipeline_page_model_enables_midi_rerun_only_with_result() -> None:
    model = PipelinePageModel(busy=False, has_result=True, generate_midi=True)

    assert model.drop_zone_enabled is True
    assert model.run_full_enabled is True
    assert model.run_midi_enabled is True
    assert model.export_enabled is True
    assert model.cancel_enabled is False
    assert model.midi_stem_checks_enabled is True
