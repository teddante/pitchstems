import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

import pitchstems.separation as separation
from pitchstems.model_catalog import model_choice
from pitchstems.separation import _redirect_output, _registry_model


def test_redirect_output_captures_stderr_when_console_stream_is_missing(monkeypatch) -> None:
    messages: list[str] = []
    monkeypatch.setattr(sys, "stderr", None)

    with _redirect_output(messages.append):
        print("progress update", file=sys.stderr)

    assert messages == ["progress update"]


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
