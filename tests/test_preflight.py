from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from pitchstems.preflight import _basic_pitch_model_check, _model_registry_check, run_preflight


def test_preflight_reports_missing_ffmpeg(monkeypatch) -> None:
    def missing_ffmpeg() -> str:
        raise RuntimeError("missing ffmpeg")

    monkeypatch.setattr("pitchstems.preflight.require_ffmpeg", missing_ffmpeg)

    report = run_preflight(require_ml=False)

    assert not report.ok
    assert any(check.name == "FFmpeg" and not check.ok for check in report.checks)


def test_preflight_reports_cuda_request_without_cuda(monkeypatch) -> None:
    monkeypatch.setattr("pitchstems.preflight.require_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(
        "pitchstems.preflight.torch_status",
        lambda: SimpleNamespace(installed=True, cuda_available=False, device_name=""),
    )

    report = run_preflight(require_ml=False, requested_device="cuda")

    assert not report.ok
    assert any(check.name == "PyTorch CUDA" and not check.ok for check in report.checks)


def test_preflight_reports_missing_native_ml_packages(monkeypatch) -> None:
    monkeypatch.setattr("pitchstems.preflight.require_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(
        "pitchstems.preflight.onnxruntime_status",
        lambda: SimpleNamespace(installed=True, providers=["CPUExecutionProvider"]),
    )

    monkeypatch.setattr(
        "pitchstems.preflight._basic_pitch_model_check",
        lambda: SimpleNamespace(name="Basic Pitch", ok=False, detail="missing"),
    )
    monkeypatch.setattr(
        "pitchstems.preflight.module_check",
        lambda label, module: SimpleNamespace(name=label, ok=True, detail=module),
    )

    report = run_preflight(require_ml=True)

    assert not report.ok
    assert any(check.name == "Basic Pitch" and not check.ok for check in report.checks)
    assert any(check.name == "BS-RoFormer native backend" and check.ok for check in report.checks)


def test_preflight_reports_unwritable_output_root(monkeypatch, tmp_path: Path) -> None:
    def fake_mkstemp(**_kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr("pitchstems.preflight.tempfile.mkstemp", fake_mkstemp)
    monkeypatch.setattr("pitchstems.preflight.require_ffmpeg", lambda: "ffmpeg")

    report = run_preflight(require_ml=False, output_root=tmp_path)

    assert not report.ok
    assert "Output directory" in report.failure_summary()


def test_preflight_can_skip_model_registry_check_when_ml_not_required(monkeypatch) -> None:
    monkeypatch.setattr("pitchstems.preflight.require_ffmpeg", lambda: "ffmpeg")

    report = run_preflight(require_ml=False, model_key="bs_roformer_sw")

    assert report.ok


def test_preflight_preserves_existing_legacy_probe_filename(monkeypatch, tmp_path: Path) -> None:
    legacy_probe = tmp_path / ".pitchstems-preflight-write-test"
    legacy_probe.write_text("user data", encoding="utf-8")
    monkeypatch.setattr("pitchstems.preflight.require_ffmpeg", lambda: "ffmpeg")

    report = run_preflight(require_ml=False, output_root=tmp_path)

    assert report.ok
    assert legacy_probe.read_text(encoding="utf-8") == "user data"


def test_preflight_can_require_separation_without_transcription(monkeypatch) -> None:
    monkeypatch.setattr("pitchstems.preflight.require_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(
        "pitchstems.preflight.module_check",
        lambda label, module: SimpleNamespace(ok=True, name=label, detail=module),
    )

    report = run_preflight(require_ml=True, require_transcription=False)

    assert all(check.name != "Basic Pitch" for check in report.checks)
    assert any(check.name == "BS-RoFormer native backend" for check in report.checks)


def test_model_registry_check_imports_and_validates_requested_model(monkeypatch) -> None:
    monkeypatch.setattr(
        "pitchstems.preflight.importlib.import_module",
        lambda _name: SimpleNamespace(
            MODEL_REGISTRY={"roformer-model-bs-roformer-sw-by-jarredou": object()}
        ),
    )

    check = _model_registry_check("bs_roformer_sw")

    assert check.ok
    assert check.detail == "roformer-model-bs-roformer-sw-by-jarredou"


def test_basic_pitch_model_check_reports_loaded_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        "pitchstems.preflight.load_basic_pitch_runtime",
        lambda: (object(), "ONNX CPU"),
    )

    check = _basic_pitch_model_check()

    assert check.ok
    assert check.detail == "model loaded: ONNX CPU"


def test_basic_pitch_model_check_reports_session_failure(monkeypatch) -> None:
    def fail():
        raise RuntimeError("bad model")

    monkeypatch.setattr("pitchstems.preflight.load_basic_pitch_runtime", fail)

    check = _basic_pitch_model_check()

    assert not check.ok
    assert check.detail == "bad model"
