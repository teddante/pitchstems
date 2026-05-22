from pitchstems.model_catalog import all_model_keys, model_choice


def test_default_model_is_bs_roformer_sw() -> None:
    choice = model_choice("missing-model")

    assert choice.key == "bs_roformer_sw"
    assert choice.native_model_id == "roformer-model-bs-roformer-sw-by-jarredou"
    assert "vocals" in choice.stems
    assert "piano" in choice.stems


def test_public_model_keys_include_fixed_gui_model() -> None:
    assert "bs_roformer_sw" in all_model_keys()
