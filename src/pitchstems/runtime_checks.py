from __future__ import annotations

import importlib.util
import shutil
import sys
from dataclasses import dataclass
from typing import Protocol


class InstalledRuntimeStatusLike(Protocol):
    @property
    def installed(self) -> bool: ...


class OnnxRuntimeStatusLike(InstalledRuntimeStatusLike, Protocol):
    @property
    def providers(self) -> list[str]: ...

    @property
    def has_cuda(self) -> bool: ...


class TorchStatusLike(InstalledRuntimeStatusLike, Protocol):
    @property
    def cuda_available(self) -> bool: ...

    @property
    def device_name(self) -> str | None: ...


@dataclass(frozen=True)
class RuntimeCheck:
    name: str
    ok: bool
    detail: str


def command_check(name: str, command: str) -> RuntimeCheck:
    path = shutil.which(command)
    return RuntimeCheck(name=name, ok=bool(path), detail=path or f"`{command}` was not found on PATH")


def python_check() -> RuntimeCheck:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    ok = sys.version_info[:2] == (3, 10)
    detail = f"{version} detected; Python 3.10 is recommended for Basic Pitch on Windows"
    return RuntimeCheck(name="Python", ok=ok, detail=detail)


def module_check(name: str, module_name: str) -> RuntimeCheck:
    found = importlib.util.find_spec(module_name) is not None
    return RuntimeCheck(name=name, ok=found, detail="installed" if found else f"`{module_name}` missing")


def onnxruntime_check(status: OnnxRuntimeStatusLike) -> RuntimeCheck:
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


def onnxruntime_cuda_check(status: OnnxRuntimeStatusLike) -> RuntimeCheck:
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


def torch_cuda_check(status: TorchStatusLike) -> RuntimeCheck:
    if not status.installed:
        return RuntimeCheck(name="PyTorch CUDA", ok=False, detail="`torch` missing")
    detail = status.device_name if status.cuda_available else "CUDA is not available to PyTorch"
    return RuntimeCheck(name="PyTorch CUDA", ok=status.cuda_available, detail=detail or "")


def _provider_detail(status: OnnxRuntimeStatusLike) -> str:
    return ", ".join(status.providers) or "no providers"
