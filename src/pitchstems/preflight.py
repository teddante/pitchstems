from __future__ import annotations

from dataclasses import dataclass

from pitchstems.acceleration import onnxruntime_status, torch_status
from pitchstems.audio import require_ffmpeg


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class PreflightReport:
    checks: list[PreflightCheck]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    def failure_summary(self) -> str:
        failures = [f"{check.name}: {check.detail}" for check in self.checks if not check.ok]
        return "; ".join(failures)


def run_preflight(require_ml: bool = True, requested_device: str | None = None) -> PreflightReport:
    checks: list[PreflightCheck] = []
    try:
        checks.append(PreflightCheck("FFmpeg", True, require_ffmpeg()))
    except Exception as exc:
        checks.append(PreflightCheck("FFmpeg", False, str(exc)))

    if requested_device == "cuda":
        status = torch_status()
        checks.append(
            PreflightCheck(
                "PyTorch CUDA",
                bool(status.installed and status.cuda_available),
                status.device_name if status.cuda_available else "CUDA is not available to PyTorch",
            )
        )

    if require_ml:
        ort = onnxruntime_status()
        checks.append(
            PreflightCheck(
                "ONNX Runtime",
                bool(ort.installed),
                ", ".join(ort.providers) if ort.installed else "ONNX Runtime is not installed",
            )
        )
    return PreflightReport(checks)
