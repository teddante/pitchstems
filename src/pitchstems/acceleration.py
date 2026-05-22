from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OnnxRuntimeStatus:
    installed: bool
    providers: list[str]

    @property
    def has_cuda(self) -> bool:
        return "CUDAExecutionProvider" in self.providers


@dataclass(frozen=True)
class TorchStatus:
    installed: bool
    cuda_available: bool
    device_name: str | None = None


def onnxruntime_status() -> OnnxRuntimeStatus:
    try:
        import onnxruntime as ort
    except ImportError:
        return OnnxRuntimeStatus(installed=False, providers=[])

    return OnnxRuntimeStatus(installed=True, providers=list(ort.get_available_providers()))


def torch_status() -> TorchStatus:
    try:
        import torch
    except ImportError:
        return TorchStatus(installed=False, cuda_available=False)

    cuda_available = bool(torch.cuda.is_available())
    device_name = torch.cuda.get_device_name(0) if cuda_available else None
    return TorchStatus(installed=True, cuda_available=cuda_available, device_name=device_name)

