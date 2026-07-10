from __future__ import annotations

import importlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from pitchstems.acceleration import onnxruntime_status, torch_status
from pitchstems.audio import require_ffmpeg
from pitchstems.runtime_checks import (
    RuntimeCheck as PreflightCheck,
    module_check,
    onnxruntime_check,
    torch_cuda_check,
)
from pitchstems.transcription import load_basic_pitch_runtime


@dataclass(frozen=True)
class PreflightReport:
    checks: list[PreflightCheck]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    def failure_summary(self) -> str:
        failures = [f"{check.name}: {check.detail}" for check in self.checks if not check.ok]
        return "; ".join(failures)


def _output_directory_check(output_root: Path) -> PreflightCheck:
    probe: Path | None = None
    try:
        output_root.mkdir(parents=True, exist_ok=True)
        descriptor, probe_name = tempfile.mkstemp(
            prefix=".pitchstems-preflight-",
            dir=output_root,
        )
        probe = Path(probe_name)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write("ok")
        return PreflightCheck("Output directory", True, f"writable: {output_root}")
    except Exception as exc:
        return PreflightCheck("Output directory", False, str(exc))
    finally:
        if probe is not None:
            probe.unlink(missing_ok=True)


def _model_registry_check(model_key: str) -> PreflightCheck:
    try:
        from pitchstems.model_catalog import model_choice

        backend = importlib.import_module("bs_roformer")
        registry = getattr(backend, "MODEL_REGISTRY")
        choice = model_choice(model_key)
        if registry.get(choice.native_model_id) is None:
            return PreflightCheck("BS-RoFormer model registry", False, choice.native_model_id)
        return PreflightCheck("BS-RoFormer model registry", True, choice.native_model_id)
    except Exception as exc:
        return PreflightCheck("BS-RoFormer model registry", False, str(exc))


def _basic_pitch_model_check() -> PreflightCheck:
    try:
        _model, runtime = load_basic_pitch_runtime()
        return PreflightCheck("Basic Pitch", True, f"model loaded: {runtime}")
    except Exception as exc:
        return PreflightCheck("Basic Pitch", False, str(exc))


def run_preflight(
    require_ml: bool = True,
    require_transcription: bool | None = None,
    requested_device: str | None = None,
    output_root: Path | None = None,
    model_key: str | None = None,
) -> PreflightReport:
    if require_transcription is None:
        require_transcription = require_ml
    checks: list[PreflightCheck] = []
    try:
        checks.append(PreflightCheck("FFmpeg", True, require_ffmpeg()))
    except Exception as exc:
        checks.append(PreflightCheck("FFmpeg", False, str(exc)))

    if output_root is not None:
        checks.append(_output_directory_check(output_root))

    if requested_device and requested_device.startswith("cuda"):
        checks.append(torch_cuda_check(torch_status()))

    if require_transcription:
        checks.append(onnxruntime_check(onnxruntime_status()))
        checks.append(_basic_pitch_model_check())
    if require_ml:
        checks.append(module_check("BS-RoFormer native backend", "bs_roformer"))
        if model_key:
            checks.append(_model_registry_check(model_key))
    return PreflightReport(checks)
