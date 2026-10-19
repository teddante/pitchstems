import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

import pitchstems.separation as separation
from pitchstems.model_catalog import model_choice
from pitchstems.pipeline_models import StemResult
from pitchstems.separation import (
    _redirect_output,
    _registry_model,
    _retain_selected_stem,
)


def test_redirect_output_captures_stderr_when_console_stream_is_missing(monkeypatch) -> None:
    messages: list[str] = []
    monkeypatch.setattr(sys, "stderr", None)

    with _redirect_output(messages.append):
        print("progress update", file=sys.stderr)

    assert messages == ["progress update"]


def test_redirect_output_can_forward_to_print_logger(capsys) -> None:
    with _redirect_output(print):
        print("native progress")

    assert "native progress" in capsys.readouterr().out


def test_registry_model_reports_missing_native_model_id() -> None:
    with pytest.raises(RuntimeError, match="registry id is unavailable"):
        _registry_model({}, model_choice("bs_roformer_sw"))


def test_separation_fails_when_native_backend_produces_no_stems(
    tmp_path: Path,
    monkeypatch,
) -> None:
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"wav")
    native_model = SimpleNamespace(slug="", checkpoint="model.ckpt", config="model.yaml")
    bs_roformer = ModuleType("bs_roformer")
    bs_roformer.MODEL_REGISTRY = {}
    inference = ModuleType("bs_roformer.inference")
    inference.proc_folder = lambda _args: None

    monkeypatch.setattr(separation, "download_model", lambda *_args, **_kwargs: tmp_path)
    monkeypatch.setattr(separation, "_registry_model", lambda *_args: native_model)
    monkeypatch.setitem(sys.modules, "bs_roformer", bs_roformer)
    monkeypatch.setitem(sys.modules, "bs_roformer.inference", inference)
    (tmp_path / "model.ckpt").write_text("weights", encoding="utf-8")
    (tmp_path / "model.yaml").write_text("config", encoding="utf-8")

    with pytest.raises(RuntimeError, match="did not produce any stems"):
        separation.separate_stems(audio, tmp_path / "out")


def test_default_model_reuses_model_catalog_stems_and_registry_id() -> None:
    choice = model_choice("bs_roformer_sw")
    assert choice.stems == ["vocals", "drums", "bass", "guitar", "piano", "other", "instrumental"]
    assert choice.native_model_id == "roformer-model-bs-roformer-sw-by-jarredou"


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


def test_separation_passes_native_backend_a_folder_with_only_the_input(
    tmp_path: Path,
    monkeypatch,
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    audio = work / "song.wav"
    audio.write_bytes(b"wav")
    (work / "leftover.wav").write_bytes(b"other")
    native_model = SimpleNamespace(slug="", checkpoint="model.ckpt", config="model.yaml")
    seen: list[list[str]] = []

    def fake_proc_folder(args) -> None:
        seen.append(sorted(path.name for path in Path(args.input_folder).iterdir()))
        (Path(args.store_dir) / "song_bass.wav").write_bytes(b"stem")

    bs_roformer = ModuleType("bs_roformer")
    bs_roformer.MODEL_REGISTRY = {}
    inference = ModuleType("bs_roformer.inference")
    inference.proc_folder = fake_proc_folder
    monkeypatch.setattr(separation, "download_model", lambda *_args, **_kwargs: tmp_path)
    monkeypatch.setattr(separation, "_registry_model", lambda *_args: native_model)
    monkeypatch.setitem(sys.modules, "bs_roformer", bs_roformer)
    monkeypatch.setitem(sys.modules, "bs_roformer.inference", inference)
    (tmp_path / "model.ckpt").write_text("weights", encoding="utf-8")
    (tmp_path / "model.yaml").write_text("config", encoding="utf-8")

    stems = separation.separate_stems(audio, tmp_path / "out")

    assert seen == [["song.wav"]]
    assert [stem.name for stem in stems] == ["bass"]
    assert sorted(path.name for path in work.iterdir()) == ["leftover.wav", "song.wav"]


def _install_fake_backend(tmp_path: Path, monkeypatch, proc_folder) -> None:
    native_model = SimpleNamespace(slug="", checkpoint="model.ckpt", config="model.yaml")
    bs_roformer = ModuleType("bs_roformer")
    bs_roformer.MODEL_REGISTRY = {}
    inference = ModuleType("bs_roformer.inference")
    inference.proc_folder = proc_folder
    monkeypatch.setattr(separation, "download_model", lambda *_args, **_kwargs: tmp_path)
    monkeypatch.setattr(separation, "_registry_model", lambda *_args: native_model)
    monkeypatch.setitem(sys.modules, "bs_roformer", bs_roformer)
    monkeypatch.setitem(sys.modules, "bs_roformer.inference", inference)
    (tmp_path / "model.ckpt").write_text("weights", encoding="utf-8")
    (tmp_path / "model.yaml").write_text("config", encoding="utf-8")


@pytest.mark.parametrize("input_stem", ["song", "my_vocals_take", "song_guitar_demo", "Drums___Bass"])
def test_separation_keeps_every_stem_when_input_name_contains_stem_words(
    tmp_path: Path,
    monkeypatch,
    input_stem: str,
) -> None:
    instruments = model_choice("bs_roformer_sw").stems
    audio = tmp_path / f"{input_stem}.wav"
    audio.write_bytes(b"wav")

    def fake_proc_folder(args) -> None:
        for path in Path(args.input_folder).glob("*.wav"):
            for instrument in instruments:
                (Path(args.store_dir) / f"{path.stem}_{instrument}.wav").write_bytes(b"stem")

    _install_fake_backend(tmp_path, monkeypatch, fake_proc_folder)

    stems = separation.separate_stems(audio, tmp_path / "out")

    assert sorted(stem.name for stem in stems) == sorted(instruments)
    assert all(stem.path.name == f"{input_stem}_{stem.name}.wav" for stem in stems)


def test_separation_rejects_two_outputs_for_one_stem_instead_of_dropping_one(
    tmp_path: Path,
    monkeypatch,
) -> None:
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"wav")

    def fake_proc_folder(args) -> None:
        (Path(args.store_dir) / "song_bass.wav").write_bytes(b"stem")
        (Path(args.store_dir) / "bass.wav").write_bytes(b"stem")

    _install_fake_backend(tmp_path, monkeypatch, fake_proc_folder)

    with pytest.raises(RuntimeError, match="two outputs for stem"):
        separation.separate_stems(audio, tmp_path / "out")
