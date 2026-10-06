from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pitchstems.runtime_checks as runtime_checks
from pitchstems.acceleration import OnnxRuntimeStatus, TorchStatus
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


def test_preflight_can_skip_model_registry_check_when_ml_not_required(monkeypatch) -> None:
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


def test_model_registry_check_imports_and_validates_requested_model(monkeypatch) -> None:
    monkeypatch.setattr(
        "pitchstems.runtime_checks.importlib.import_module",
        lambda _name: SimpleNamespace(
            MODEL_REGISTRY={"roformer-model-bs-roformer-sw-by-jarredou": object()}
        ),
    )

    check = model_registry_check("bs_roformer_sw")

    assert check.ok
    assert check.detail == "roformer-model-bs-roformer-sw-by-jarredou"


def test_basic_pitch_check_reports_loaded_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        "pitchstems.runtime_checks.load_basic_pitch_runtime",
        lambda: (object(), "ONNX CPU"),
    )

    check = basic_pitch_check()

    assert check.ok
    assert check.detail == "model loaded: ONNX CPU"


def test_basic_pitch_check_reports_session_failure(monkeypatch) -> None:
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


def test_command_check_reports_path_or_missing_command(monkeypatch) -> None:
    monkeypatch.setattr(runtime_checks.shutil, "which", lambda name: "/bin/ffmpeg" if name == "ffmpeg" else None)

    assert runtime_checks.command_check("FFmpeg", "ffmpeg") == RuntimeCheck("FFmpeg", True, "/bin/ffmpeg")
    missing = runtime_checks.command_check("NVIDIA driver", "nvidia-smi")
    assert not missing.ok
    assert "`nvidia-smi` was not found on PATH" == missing.detail


def test_python_check_reports_running_version() -> None:
    check = runtime_checks.python_check()

    assert check.name == "Python"
    assert "supports Python 3.10 and 3.11" in check.detail


def test_module_check_reports_first_line_of_import_failure() -> None:
    check = runtime_checks.module_check("Missing", "pitchstems_definitely_missing_module")

    assert not check.ok
    assert check.detail.startswith("`pitchstems_definitely_missing_module` import failed:")
    assert runtime_checks.module_check("MIDI tools", "json").ok


def test_gpu_checks_report_missing_and_available_runtimes() -> None:
    assert not runtime_checks.onnxruntime_cuda_check(OnnxRuntimeStatus(installed=False, providers=[])).ok
    cuda = runtime_checks.onnxruntime_cuda_check(
        OnnxRuntimeStatus(installed=True, providers=["CUDAExecutionProvider"])
    )
    assert cuda.ok and "CUDAExecutionProvider" in cuda.detail
    cpu_only = runtime_checks.onnxruntime_cuda_check(OnnxRuntimeStatus(installed=True, providers=[]))
    assert not cpu_only.ok and cpu_only.detail == "providers: no providers"

    assert runtime_checks.torch_cuda_check(TorchStatus(installed=False, cuda_available=False)).detail == "`torch` missing"
    no_cuda = runtime_checks.torch_cuda_check(TorchStatus(installed=True, cuda_available=False))
    assert not no_cuda.ok and no_cuda.detail == "CUDA is not available to PyTorch"
    gpu = runtime_checks.torch_cuda_check(
        TorchStatus(installed=True, cuda_available=True, device_name="RTX")
    )
    assert gpu == RuntimeCheck("PyTorch CUDA", True, "RTX")


def test_run_checks_adds_gpu_checks_and_formats_status(monkeypatch) -> None:
    monkeypatch.setattr(runtime_checks.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        runtime_checks,
        "onnxruntime_status",
        lambda: OnnxRuntimeStatus(installed=True, providers=["CPUExecutionProvider"]),
    )
    monkeypatch.setattr(runtime_checks, "torch_status", lambda: TorchStatus(installed=False, cuda_available=False))
    monkeypatch.setattr(runtime_checks, "load_basic_pitch_runtime", lambda: (object(), "ONNX CPU"))

    checks = runtime_checks.run_checks(require_gpu=True)
    names = [check.name for check in checks]

    assert names[-3:] == ["NVIDIA driver", "ONNX Runtime CUDA", "PyTorch CUDA"]
    text = runtime_checks.format_checks(checks)
    assert "MISSING FFmpeg:" in text
    assert "OK      Basic Pitch: model loaded: ONNX CPU" in text


def test_model_registry_check_reports_unknown_model_and_import_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "pitchstems.runtime_checks.importlib.import_module",
        lambda _name: SimpleNamespace(MODEL_REGISTRY={}),
    )
    assert not model_registry_check("bs_roformer_sw").ok

    def fail(_name):
        raise ImportError("no backend")

    monkeypatch.setattr("pitchstems.runtime_checks.importlib.import_module", fail)
    check = model_registry_check("bs_roformer_sw")
    assert not check.ok and check.detail == "no backend"


def test_run_setup_reports_repair_failure_with_current_statuses(monkeypatch, tmp_path: Path) -> None:
    logs: list[str] = []
    statuses = [ModelAssetStatus("model.bin", tmp_path / "model.bin", False, "missing")]
    monkeypatch.setattr(runtime_checks, "run_checks", lambda require_gpu: [])

    def fail(*_args, **_kwargs):
        raise RuntimeError("download failed")

    monkeypatch.setattr(runtime_checks, "ensure_model_assets", fail)
    monkeypatch.setattr(runtime_checks, "model_asset_statuses", lambda *_args, **_kwargs: statuses)

    result = runtime_checks.run_setup(log=logs.append)

    assert not result.ok
    assert logs == ["Setup repair failed: download failed"]
    text = runtime_checks.format_setup_result(result)
    assert "NEEDS FIX model.bin: missing" in text
    assert "Setup error: download failed" in text
