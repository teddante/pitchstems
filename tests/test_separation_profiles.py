from pitchstems.model_catalog import model_choice
from pitchstems.separation import get_profile, model_key_for_profile


def test_model_key_for_profile_resolves_current_and_legacy_profiles() -> None:
    assert model_key_for_profile("song-6-stem") == "bs_roformer_sw"
    assert model_key_for_profile("best") == "bs_roformer_sw"


def test_default_profile_reuses_model_catalog_stems_and_registry_id() -> None:
    choice = model_choice("bs_roformer_sw")
    profile = get_profile("song-6-stem")

    assert profile.expected_stems == choice.stems
    assert profile.models == [choice.native_model_id]
