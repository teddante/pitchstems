from __future__ import annotations

import importlib
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
