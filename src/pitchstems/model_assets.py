from __future__ import annotations

import hashlib
import os
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from pitchstems.model_catalog import DEFAULT_MODEL_KEY, model_choice


@dataclass(frozen=True)
class HuggingFaceAssetSource:
    repo_id: str
    path: str
    label: str


@dataclass(frozen=True)
class ModelAsset:
    filename: str
    size: int
    sha256: str
    sources: tuple[HuggingFaceAssetSource, ...]


@dataclass(frozen=True)
class ModelAssetStatus:
    filename: str
    path: Path
    ok: bool
    detail: str


class ModelAssetDownloadError(RuntimeError):
    """Raised when a model asset cannot be downloaded from any configured source."""


_BS_ROFORMER_SW_MODEL = model_choice(DEFAULT_MODEL_KEY)


BS_ROFORMER_SW_ASSETS = (
    ModelAsset(
        filename=_BS_ROFORMER_SW_MODEL.filename,
        size=699_412_152,
        sha256="24e7d35ee9c64415673d3fd33e06a67cac2c103c5df6267ba1576459c775916e",
        sources=(
            HuggingFaceAssetSource(
                repo_id="jarredou/BS-ROFO-SW-Fixed",
                path=_BS_ROFORMER_SW_MODEL.filename,
                label="original publisher",
            ),
            HuggingFaceAssetSource(
                repo_id="lainlives/audio-separator-models",
                path="BS-Roformer-SW.ckpt",
                label="checksum-matched Hugging Face copy",
            ),
        ),
    ),
    ModelAsset(
        filename=_BS_ROFORMER_SW_MODEL.config_filename,
        size=4_653,
        sha256="b558996f1e25eb48798bd6502505a5de94c4f966d6edfb1a0420f06cc40b501a",
        sources=(
            HuggingFaceAssetSource(
                repo_id="jarredou/BS-ROFO-SW-Fixed",
                path=_BS_ROFORMER_SW_MODEL.config_filename,
                label="original publisher",
            ),
            HuggingFaceAssetSource(
                repo_id="lainlives/audio-separator-models",
                path="BS-Roformer-SW.yaml",
                label="checksum-matched Hugging Face copy",
            ),
        ),
    ),
)


MODEL_ASSETS = {
    DEFAULT_MODEL_KEY: BS_ROFORMER_SW_ASSETS,
}


def model_cache_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if root:
        return Path(root) / "PitchStems" / "bs-roformer-models"
    return Path.home() / ".cache" / "pitchstems" / "bs-roformer-models"


def model_asset_dir(model_key: str, cache_root: Path | None = None) -> Path:
    return (cache_root or model_cache_dir()) / model_choice(model_key).native_model_id


def model_asset_statuses(
    model_key: str,
    *,
    cache_root: Path | None = None,
    verify_hash: bool = False,
) -> list[ModelAssetStatus]:
    directory = model_asset_dir(model_key, cache_root=cache_root)
    assets = _assets_for(model_key)
    return [
        _asset_status(asset, directory / asset.filename, verify_hash=verify_hash)
        for asset in assets
    ]


def ensure_model_assets(
    model_key: str,
    *,
    cache_root: Path | None = None,
    log: Callable[[str], None] | None = None,
    verify_hash: bool = False,
) -> list[ModelAssetStatus]:
    """Ensure the backend's model files exist, fully verifying cached files on request."""
    assets = _assets_for(model_key)

    directory = model_asset_dir(model_key, cache_root=cache_root)
    directory.mkdir(parents=True, exist_ok=True)
    statuses: list[ModelAssetStatus] = []

    for asset in assets:
        target = directory / asset.filename
        status = _asset_status(asset, target, verify_hash=verify_hash)
        if status.ok:
            statuses.append(status)
            continue
        if target.exists():
            _log(log, f"Repairing {asset.filename}: {status.detail}")
        statuses.append(_download_asset(asset, target, log=log))

    return statuses


def _asset_status(asset: ModelAsset, path: Path, *, verify_hash: bool) -> ModelAssetStatus:
    if not path.exists():
        return ModelAssetStatus(asset.filename, path, False, "missing")
    size = path.stat().st_size
    if size != asset.size:
        return ModelAssetStatus(
            asset.filename,
            path,
            False,
            f"size mismatch: expected {asset.size:,} bytes, found {size:,}",
        )
    if verify_hash:
        actual = _sha256(path)
        if actual != asset.sha256:
            return ModelAssetStatus(
                asset.filename,
                path,
                False,
                f"sha256 mismatch: expected {asset.sha256}, found {actual}",
            )
    return ModelAssetStatus(asset.filename, path, True, "verified" if verify_hash else "present")


def _download_asset(
    asset: ModelAsset,
    target: Path,
    *,
    log: Callable[[str], None] | None,
) -> ModelAssetStatus:
    errors: list[str] = []
    for source in asset.sources:
        try:
            _log(log, f"Downloading {asset.filename} from {source.label} ({source.repo_id})...")
            downloaded = _hf_download(source)
            status = _asset_status(asset, downloaded, verify_hash=True)
            if not status.ok:
                raise ModelAssetDownloadError(status.detail)
        except Exception as exc:
            errors.append(f"{source.label} ({source.repo_id}/{source.path}): {exc}")
            _log(log, f"Could not download {asset.filename} from {source.label}: {exc}")
            continue

        part = target.with_name(
            f".{target.name}.{os.getpid()}.{threading.get_ident()}.part"
        )
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(downloaded, part)
            part.replace(target)
        except OSError as exc:
            raise ModelAssetDownloadError(
                f"Downloaded {asset.filename}, but could not cache it at {target}: {exc}"
            ) from exc
        finally:
            part.unlink(missing_ok=True)
        _log(log, f"Cached {asset.filename}: {target}")
        return ModelAssetStatus(asset.filename, target, True, "verified")
    joined = "\n".join(f"- {error}" for error in errors)
    raise ModelAssetDownloadError(f"Failed to download {asset.filename} from candidate sources:\n{joined}")


def _hf_download(source: HuggingFaceAssetSource) -> Path:
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise ModelAssetDownloadError(
            "huggingface-hub is not installed. Install the PitchStems ML extras, "
            "then run `pitchstems --setup` again."
        ) from exc

    return Path(
        hf_hub_download(
            repo_id=source.repo_id,
            filename=source.path,
        )
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _log(log: Callable[[str], None] | None, message: str) -> None:
    if log is not None:
        log(message)


def _assets_for(model_key: str) -> tuple[ModelAsset, ...]:
    assets = MODEL_ASSETS.get(model_key)
    if not assets:
        raise KeyError(f"No model asset manifest for {model_key!r}")
    return assets
