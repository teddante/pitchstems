from __future__ import annotations

from pitchstems.acceleration import onnxruntime_status, torch_status
from pitchstems.runtime_checks import (
    RuntimeCheck as Check,
    command_check,
    module_check,
    onnxruntime_check,
    onnxruntime_cuda_check,
    python_check,
    torch_cuda_check,
)


def run_checks(require_gpu: bool = False) -> list[Check]:
    checks = [
        python_check(),
        command_check("FFmpeg", "ffmpeg"),
        module_check("PySide6 GUI", "PySide6"),
        module_check("Basic Pitch", "basic_pitch"),
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


def format_checks(checks: list[Check]) -> str:
    lines = []
    for check in checks:
        status = "OK" if check.ok else "MISSING"
        lines.append(f"{status:7} {check.name}: {check.detail}")
    return "\n".join(lines)
