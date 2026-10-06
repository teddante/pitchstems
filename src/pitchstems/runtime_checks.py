"""Runtime environment checks: primitives, `--doctor`, pipeline preflight, and setup repair."""

from __future__ import annotations

import importlib
import os
import shutil
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pitchstems.acceleration import (
    OnnxRuntimeStatus,
    TorchStatus,
    onnxruntime_status,
    torch_status,
)
from pitchstems.audio import require_ffmpeg
from pitchstems.model_assets import ModelAssetStatus, ensure_model_assets, model_asset_statuses
from pitchstems.model_catalog import DEFAULT_MODEL_KEY, model_choice
from pitchstems.transcription import load_basic_pitch_runtime


@dataclass(frozen=True)
class RuntimeCheck:
    name: str
    ok: bool
    detail: str


# Primitive checks


def command_check(name: str, command: str) -> RuntimeCheck:
    path = shutil.which(command)
    return RuntimeCheck(name=name, ok=bool(path), detail=path or f"`{command}` was not found on PATH")


def python_check() -> RuntimeCheck:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    ok = (3, 10) <= sys.version_info[:2] < (3, 12)
    detail = f"{version} detected; PitchStems supports Python 3.10 and 3.11"
    return RuntimeCheck(name="Python", ok=ok, detail=detail)


def module_check(name: str, module_name: str) -> RuntimeCheck:
    try:
        importlib.import_module(module_name)
    except Exception as exc:
        detail = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        return RuntimeCheck(name=name, ok=False, detail=f"`{module_name}` import failed: {detail}")
    return RuntimeCheck(name=name, ok=True, detail="imported successfully")


def ffmpeg_check() -> RuntimeCheck:
    try:
        return RuntimeCheck("FFmpeg", True, require_ffmpeg())
    except Exception as exc:
        return RuntimeCheck("FFmpeg", False, str(exc))


def basic_pitch_check() -> RuntimeCheck:
    try:
        _model, runtime = load_basic_pitch_runtime()
        return RuntimeCheck("Basic Pitch", True, f"model loaded: {runtime}")
    except Exception as exc:
        return RuntimeCheck("Basic Pitch", False, str(exc))


def onnxruntime_check(status: OnnxRuntimeStatus) -> RuntimeCheck:
    if not status.installed:
        return RuntimeCheck(
            name="ONNX Runtime",
            ok=False,
            detail="`onnxruntime` or `onnxruntime-gpu` missing",
        )
    return RuntimeCheck(
        name="ONNX Runtime",
        ok=True,
        detail=f"providers: {_provider_detail(status)}",
    )


def onnxruntime_cuda_check(status: OnnxRuntimeStatus) -> RuntimeCheck:
    if not status.installed:
        return RuntimeCheck(
            name="ONNX Runtime CUDA",
            ok=False,
            detail="`onnxruntime-gpu` missing",
        )
    return RuntimeCheck(
        name="ONNX Runtime CUDA",
        ok=status.has_cuda,
        detail=f"providers: {_provider_detail(status)}",
    )


def torch_cuda_check(status: TorchStatus) -> RuntimeCheck:
    if not status.installed:
        return RuntimeCheck(name="PyTorch CUDA", ok=False, detail="`torch` missing")
    detail = status.device_name if status.cuda_available else "CUDA is not available to PyTorch"
    return RuntimeCheck(name="PyTorch CUDA", ok=status.cuda_available, detail=detail or "")


def output_directory_check(output_root: Path) -> RuntimeCheck:
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
        return RuntimeCheck("Output directory", True, f"writable: {output_root}")
    except Exception as exc:
        return RuntimeCheck("Output directory", False, str(exc))
    finally:
        if probe is not None:
            probe.unlink(missing_ok=True)


def model_registry_check(model_key: str) -> RuntimeCheck:
    try:
        backend = importlib.import_module("bs_roformer")
        registry = backend.MODEL_REGISTRY
        choice = model_choice(model_key)
        if registry.get(choice.native_model_id) is None:
            return RuntimeCheck("BS-RoFormer model registry", False, choice.native_model_id)
        return RuntimeCheck("BS-RoFormer model registry", True, choice.native_model_id)
    except Exception as exc:
        return RuntimeCheck("BS-RoFormer model registry", False, str(exc))


def _provider_detail(status: OnnxRuntimeStatus) -> str:
    return ", ".join(status.providers) or "no providers"


# Doctor (`pitchstems --doctor`)


def run_checks(require_gpu: bool = False) -> list[RuntimeCheck]:
    checks = [
        python_check(),
        ffmpeg_check(),
        module_check("PySide6 GUI", "PySide6"),
        basic_pitch_check(),
        onnxruntime_check(onnxruntime_status()),
        module_check("BS-RoFormer native backend", "bs_roformer"),
        module_check("MIDI tools", "mido"),
    ]
    if require_gpu:
        checks.extend(
            [
                command_check("NVIDIA driver", "nvidia-smi"),
                onnxruntime_cuda_check(onnxruntime_status()),
                torch_cuda_check(torch_status()),
            ]
        )
    return checks


def format_checks(checks: list[RuntimeCheck]) -> str:
    lines = []
    for check in checks:
        status = "OK" if check.ok else "MISSING"
        lines.append(f"{status:7} {check.name}: {check.detail}")
    return "\n".join(lines)


# Pipeline preflight


@dataclass(frozen=True)
class PreflightReport:
    checks: list[RuntimeCheck]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    def failure_summary(self) -> str:
        failures = [f"{check.name}: {check.detail}" for check in self.checks if not check.ok]
        return "; ".join(failures)


def run_preflight(
    require_ml: bool = True,
    require_transcription: bool | None = None,
    requested_device: str | None = None,
    output_root: Path | None = None,
    model_key: str | None = None,
) -> PreflightReport:
    if require_transcription is None:
        require_transcription = require_ml
    checks = [ffmpeg_check()]
    if output_root is not None:
        checks.append(output_directory_check(output_root))
    if requested_device and requested_device.startswith("cuda"):
        checks.append(torch_cuda_check(torch_status()))
    if require_transcription:
        checks.append(onnxruntime_check(onnxruntime_status()))
        checks.append(basic_pitch_check())
    if require_ml:
        checks.append(module_check("BS-RoFormer native backend", "bs_roformer"))
        if model_key:
            checks.append(model_registry_check(model_key))
    return PreflightReport(checks)


# Setup repair (`pitchstems --setup` and the GUI Repair Setup button)


@dataclass(frozen=True)
class RuntimeSetupResult:
    checks: list[RuntimeCheck]
    model_statuses: list[ModelAssetStatus]
    error: str | None = None

    @property
    def ok(self) -> bool:
        return (
            self.error is None
            and all(check.ok for check in self.checks)
            and all(status.ok for status in self.model_statuses)
        )


def run_setup(
    *,
    log: Callable[[str], None] | None = None,
) -> RuntimeSetupResult:
    checks = run_checks(require_gpu=False)
    statuses: list[ModelAssetStatus]
    error = None
    try:
        statuses = ensure_model_assets(DEFAULT_MODEL_KEY, log=log, verify_hash=True)
    except Exception as exc:
        error = str(exc)
        if log is not None:
            log(f"Setup repair failed: {exc}")
        statuses = model_asset_statuses(DEFAULT_MODEL_KEY, verify_hash=True)
    return RuntimeSetupResult(checks=checks, model_statuses=statuses, error=error)


def format_setup_result(result: RuntimeSetupResult) -> str:
    lines = ["Runtime checks:", format_checks(result.checks), "", "Model assets:"]
    for status in result.model_statuses:
        state = "OK" if status.ok else "NEEDS FIX"
        lines.append(f"{state:9} {status.filename}: {status.detail}")
    if result.error:
        lines.extend(["", f"Setup error: {result.error}"])
    return "\n".join(lines)
