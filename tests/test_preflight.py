from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from pitchstems.preflight import run_preflight


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
    import importlib.util

    real_find_spec = importlib.util.find_spec
    monkeypatch.setattr("pitchstems.preflight.require_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(
        "pitchstems.preflight.onnxruntime_status",
        lambda: SimpleNamespace(installed=True, providers=["CPUExecutionProvider"]),
    )

    def fake_find_spec(module_name: str):
        if module_name == "basic_pitch":
            return None
        if module_name == "bs_roformer":
            return object()
        return real_find_spec(module_name)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)

    report = run_preflight(require_ml=True)

    assert not report.ok
    assert any(check.name == "Basic Pitch" and not check.ok for check in report.checks)
    assert any(check.name == "BS-RoFormer native backend" and check.ok for check in report.checks)


def test_preflight_reports_unwritable_output_root(monkeypatch, tmp_path: Path) -> None:
    def fake_write_text(self: Path, text: str, _encoding: str = "utf-8") -> int:
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "write_text", fake_write_text)
    monkeypatch.setattr("pitchstems.preflight.require_ffmpeg", lambda: "ffmpeg")

    report = run_preflight(require_ml=False, output_root=tmp_path)

    assert not report.ok
    assert "Output directory" in report.failure_summary()


def test_preflight_can_skip_model_registry_check_when_ml_not_required(monkeypatch) -> None:
    monkeypatch.setattr("pitchstems.preflight.require_ffmpeg", lambda: "ffmpeg")

    report = run_preflight(require_ml=False, model_key="bs_roformer_sw")

    assert report.ok
