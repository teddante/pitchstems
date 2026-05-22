from __future__ import annotations

import importlib.util
import shutil
import sys
from dataclasses import dataclass

from pitchstems.acceleration import onnxruntime_status, torch_status


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def run_checks(require_gpu: bool = False) -> list[Check]:
    checks = [
        _python_check(),
        _command_check("FFmpeg", "ffmpeg"),
        _module_check("PySide6 GUI", "PySide6"),
        _module_check("Basic Pitch", "basic_pitch"),
        _module_check("BS-RoFormer native backend", "bs_roformer"),
        _module_check("MIDI tools", "mido"),
    ]
    if require_gpu:
        checks.extend(
            [
                _command_check("NVIDIA driver", "nvidia-smi"),
                _onnxruntime_cuda_check(),
                _torch_cuda_check(),
            ]
        )
    return checks


def format_checks(checks: list[Check]) -> str:
    lines = []
    for check in checks:
        status = "OK" if check.ok else "MISSING"
        lines.append(f"{status:7} {check.name}: {check.detail}")
    return "\n".join(lines)


def _command_check(name: str, command: str) -> Check:
    path = shutil.which(command)
    return Check(name=name, ok=bool(path), detail=path or f"`{command}` was not found on PATH")


def _python_check() -> Check:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    ok = sys.version_info[:2] == (3, 10)
    detail = f"{version} detected; Python 3.10 is recommended for Basic Pitch on Windows"
    return Check(name="Python", ok=ok, detail=detail)


def _module_check(name: str, module_name: str) -> Check:
    spec = importlib.util.find_spec(module_name)
    return Check(name=name, ok=bool(spec), detail="installed" if spec else f"`{module_name}` missing")


def _onnxruntime_cuda_check() -> Check:
    status = onnxruntime_status()
    if not status.installed:
        return Check(
            name="ONNX Runtime CUDA",
            ok=False,
            detail="`onnxruntime-gpu` missing",
        )
    providers = ", ".join(status.providers) or "no providers"
    return Check(
        name="ONNX Runtime CUDA",
        ok=status.has_cuda,
        detail=f"providers: {providers}",
    )


def _torch_cuda_check() -> Check:
    status = torch_status()
    if not status.installed:
        return Check(name="PyTorch CUDA", ok=False, detail="`torch` missing")
    detail = status.device_name if status.cuda_available else "CUDA is not available to PyTorch"
    return Check(name="PyTorch CUDA", ok=status.cuda_available, detail=detail)
