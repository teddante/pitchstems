from __future__ import annotations

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
