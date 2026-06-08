from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path

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


def _module_check(name: str, module_name: str) -> PreflightCheck:
    found = importlib.util.find_spec(module_name) is not None
    return PreflightCheck(name, found, "installed" if found else f"`{module_name}` missing")


def _output_directory_check(output_root: Path) -> PreflightCheck:
    try:
        output_root.mkdir(parents=True, exist_ok=True)
        probe = output_root / ".pitchstems-preflight-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return PreflightCheck("Output directory", True, f"writable: {output_root}")
    except Exception as exc:
        return PreflightCheck("Output directory", False, str(exc))


def _model_registry_check(model_key: str) -> PreflightCheck:
    try:
        from bs_roformer import MODEL_REGISTRY  # type: ignore[import-untyped]

        from pitchstems.model_catalog import model_choice

        choice = model_choice(model_key)
        if MODEL_REGISTRY.get(choice.native_model_id) is None:
            return PreflightCheck("BS-RoFormer model registry", False, choice.native_model_id)
        return PreflightCheck("BS-RoFormer model registry", True, choice.native_model_id)
    except Exception as exc:
        return PreflightCheck("BS-RoFormer model registry", False, str(exc))


def run_preflight(
    require_ml: bool = True,
    requested_device: str | None = None,
    output_root: Path | None = None,
    model_key: str | None = None,
) -> PreflightReport:
    checks: list[PreflightCheck] = []
    try:
        checks.append(PreflightCheck("FFmpeg", True, require_ffmpeg()))
    except Exception as exc:
        checks.append(PreflightCheck("FFmpeg", False, str(exc)))

    if output_root is not None:
        checks.append(_output_directory_check(output_root))

    if requested_device and requested_device.startswith("cuda"):
        status = torch_status()
        checks.append(
            PreflightCheck(
                "PyTorch CUDA",
                bool(status.installed and status.cuda_available),
                status.device_name or "CUDA is not available to PyTorch",
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
        checks.append(_module_check("Basic Pitch", "basic_pitch"))
        checks.append(_module_check("BS-RoFormer native backend", "bs_roformer"))
        if model_key:
            checks.append(_model_registry_check(model_key))
    return PreflightReport(checks)
