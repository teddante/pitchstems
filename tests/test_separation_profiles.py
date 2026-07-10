from pathlib import Path

from pitchstems.model_catalog import model_choice
from pitchstems.pipeline_models import StemResult
from pitchstems.separation import _retain_selected_stem, get_profile, model_key_for_profile


def test_model_key_for_profile_resolves_current_and_legacy_profiles() -> None:
    assert model_key_for_profile("song-6-stem") == "bs_roformer_sw"
    assert model_key_for_profile("best") == "bs_roformer_sw"


def test_default_profile_reuses_model_catalog_stems_and_registry_id() -> None:
    choice = model_choice("bs_roformer_sw")
    profile = get_profile("song-6-stem")

    assert profile.expected_stems == choice.stems
    assert profile.models == [choice.native_model_id]


def test_retain_selected_stem_removes_other_new_outputs(tmp_path: Path) -> None:
    bass = tmp_path / "bass.wav"
    drums = tmp_path / "drums.wav"
    bass.write_bytes(b"bass")
    drums.write_bytes(b"drums")

    selected = _retain_selected_stem(
        [StemResult("bass", bass), StemResult("drums", drums)],
        "bass",
    )

    assert selected == [StemResult("bass", bass)]
    assert bass.exists()
    assert not drums.exists()
