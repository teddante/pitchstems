from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pitchstems.runtime_checks as runtime_checks
from pitchstems.acceleration import OnnxRuntimeStatus
from pitchstems.model_assets import ModelAssetStatus
from pitchstems.model_catalog import DEFAULT_MODEL_KEY
from pitchstems.runtime_checks import (
    RuntimeCheck,
    basic_pitch_check,
    model_registry_check,
    run_preflight,
)


def test_doctor_checks_onnxruntime_import_for_basic_pitch(monkeypatch) -> None:
    monkeypatch.setattr(
        runtime_checks,
        "onnxruntime_status",
        lambda: OnnxRuntimeStatus(installed=True, providers=["CUDAExecutionProvider"]),
    )

    checks = runtime_checks.run_checks()

    assert any(
        check.name == "ONNX Runtime"
        and check.ok
        and "CUDAExecutionProvider" in check.detail
        for check in checks
    )


def test_doctor_reports_missing_onnxruntime(monkeypatch) -> None:
    monkeypatch.setattr(
        runtime_checks,
        "onnxruntime_status",
        lambda: OnnxRuntimeStatus(installed=False, providers=[]),
    )

    checks = runtime_checks.run_checks()

    assert any(
        check.name == "ONNX Runtime"
        and not check.ok
        and "onnxruntime-gpu" in check.detail
        for check in checks
    )


def test_preflight_reports_missing_ffmpeg(monkeypatch) -> None:
    def missing_ffmpeg() -> str:
        raise RuntimeError("missing ffmpeg")

    monkeypatch.setattr("pitchstems.runtime_checks.require_ffmpeg", missing_ffmpeg)

    report = run_preflight(require_ml=False)

    assert not report.ok
    assert any(check.name == "FFmpeg" and not check.ok for check in report.checks)


def test_preflight_reports_cuda_request_without_cuda(monkeypatch) -> None:
    monkeypatch.setattr("pitchstems.runtime_checks.require_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(
        "pitchstems.runtime_checks.torch_status",
        lambda: SimpleNamespace(installed=True, cuda_available=False, device_name=""),
    )

    report = run_preflight(require_ml=False, requested_device="cuda")

    assert not report.ok
    assert any(check.name == "PyTorch CUDA" and not check.ok for check in report.checks)


def test_preflight_reports_missing_native_ml_packages(monkeypatch) -> None:
    monkeypatch.setattr("pitchstems.runtime_checks.require_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(
        "pitchstems.runtime_checks.onnxruntime_status",
        lambda: SimpleNamespace(installed=True, providers=["CPUExecutionProvider"]),
    )

    monkeypatch.setattr(
        "pitchstems.runtime_checks.basic_pitch_check",
        lambda: SimpleNamespace(name="Basic Pitch", ok=False, detail="missing"),
    )
    monkeypatch.setattr(
        "pitchstems.runtime_checks.module_check",
        lambda label, module: SimpleNamespace(name=label, ok=True, detail=module),
    )

    report = run_preflight(require_ml=True)

    assert not report.ok
    assert any(check.name == "Basic Pitch" and not check.ok for check in report.checks)
    assert any(check.name == "BS-RoFormer native backend" and check.ok for check in report.checks)


def test_preflight_reports_unwritable_output_root(monkeypatch, tmp_path: Path) -> None:
    def fake_mkstemp(**_kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr("pitchstems.runtime_checks.tempfile.mkstemp", fake_mkstemp)
    monkeypatch.setattr("pitchstems.runtime_checks.require_ffmpeg", lambda: "ffmpeg")

    report = run_preflight(require_ml=False, output_root=tmp_path)

    assert not report.ok
    assert "Output directory" in report.failure_summary()


def test_preflight_can_skipmodel_registry_check_when_ml_not_required(monkeypatch) -> None:
    monkeypatch.setattr("pitchstems.runtime_checks.require_ffmpeg", lambda: "ffmpeg")

    report = run_preflight(require_ml=False, model_key="bs_roformer_sw")

    assert report.ok


def test_preflight_preserves_existing_legacy_probe_filename(monkeypatch, tmp_path: Path) -> None:
    legacy_probe = tmp_path / ".pitchstems-preflight-write-test"
    legacy_probe.write_text("user data", encoding="utf-8")
    monkeypatch.setattr("pitchstems.runtime_checks.require_ffmpeg", lambda: "ffmpeg")

    report = run_preflight(require_ml=False, output_root=tmp_path)

    assert report.ok
    assert legacy_probe.read_text(encoding="utf-8") == "user data"


def test_preflight_can_require_separation_without_transcription(monkeypatch) -> None:
    monkeypatch.setattr("pitchstems.runtime_checks.require_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(
        "pitchstems.runtime_checks.module_check",
        lambda label, module: SimpleNamespace(ok=True, name=label, detail=module),
    )

    report = run_preflight(require_ml=True, require_transcription=False)

    assert all(check.name != "Basic Pitch" for check in report.checks)
    assert any(check.name == "BS-RoFormer native backend" for check in report.checks)


def testmodel_registry_check_imports_and_validates_requested_model(monkeypatch) -> None:
    monkeypatch.setattr(
        "pitchstems.runtime_checks.importlib.import_module",
        lambda _name: SimpleNamespace(
            MODEL_REGISTRY={"roformer-model-bs-roformer-sw-by-jarredou": object()}
        ),
    )

    check = model_registry_check("bs_roformer_sw")

    assert check.ok
    assert check.detail == "roformer-model-bs-roformer-sw-by-jarredou"


def testbasic_pitch_check_reports_loaded_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        "pitchstems.runtime_checks.load_basic_pitch_runtime",
        lambda: (object(), "ONNX CPU"),
    )

    check = basic_pitch_check()

    assert check.ok
    assert check.detail == "model loaded: ONNX CPU"


def testbasic_pitch_check_reports_session_failure(monkeypatch) -> None:
    def fail():
        raise RuntimeError("bad model")

    monkeypatch.setattr("pitchstems.runtime_checks.load_basic_pitch_runtime", fail)

    check = basic_pitch_check()

    assert not check.ok
    assert check.detail == "bad model"


def test_run_setup_uses_shared_full_model_verification(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    statuses = [ModelAssetStatus("model.bin", tmp_path / "model.bin", True, "verified")]

    monkeypatch.setattr(
        runtime_checks,
        "run_checks",
        lambda require_gpu: [RuntimeCheck("Python", not require_gpu, "installed")],
    )

    def fake_ensure(model_key: str, *, log, verify_hash: bool):
        captured.update(model_key=model_key, log=log, verify_hash=verify_hash)
        return statuses

    monkeypatch.setattr(runtime_checks, "ensure_model_assets", fake_ensure)

    result = runtime_checks.run_setup(log=print)

    assert result.ok is True
    assert captured == {
        "model_key": DEFAULT_MODEL_KEY,
        "log": print,
        "verify_hash": True,
    }
    assert "OK        model.bin: verified" in runtime_checks.format_setup_result(result)
