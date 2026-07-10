from pathlib import Path

from pitchstems import setup_runtime
from pitchstems.model_assets import ModelAssetStatus
from pitchstems.model_catalog import DEFAULT_MODEL_KEY
from pitchstems.runtime_checks import RuntimeCheck


def test_run_setup_uses_shared_full_model_verification(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    statuses = [ModelAssetStatus("model.bin", tmp_path / "model.bin", True, "verified")]

    monkeypatch.setattr(
        setup_runtime,
        "run_checks",
        lambda require_gpu: [RuntimeCheck("Python", not require_gpu, "installed")],
    )

    def fake_ensure(model_key: str, *, log, verify_hash: bool):
        captured.update(model_key=model_key, log=log, verify_hash=verify_hash)
        return statuses

    monkeypatch.setattr(setup_runtime, "ensure_model_assets", fake_ensure)

    result = setup_runtime.run_setup(log=print)

    assert result.ok is True
    assert captured == {
        "model_key": DEFAULT_MODEL_KEY,
        "log": print,
        "verify_hash": True,
    }
    assert "OK        model.bin: verified" in setup_runtime.format_setup_result(result)
